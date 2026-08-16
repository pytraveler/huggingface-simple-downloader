"""The queue: N files at a time, one progress figure for all of them.

Everything in here runs on worker threads and nothing in here touches tkinter.
The window polls `snapshot()` on a timer and drains `events`; that is the whole
contract between the two halves, and it is the reason the GUI cannot be wedged
by a stalled socket.

Two measurements are less obvious than they look.

**Resumed bytes count towards done, but not towards speed.** A file that is
already 80% on disk starts at 80% - anything else makes the bar jump backwards
on a resume - but those bytes did not come down the wire just now, so they are
kept out of the rate. Hence `done` (absolute, per file) and `_moved` (what this
run actually transferred) are separate counters.

**The rate is measured over a window, not since the start.** Five seconds is
short enough to react when a mirror slows down and long enough not to flicker
between chunks. Averaging since the start would keep quoting a speed from ten
minutes ago, and an ETA built on it would be wrong in the one direction that
annoys people - optimistic.
"""

from __future__ import annotations

import copy
import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import i18n, transfer
from .fmt import human_size
from .hub import make_client
from .i18n import Failure, Text

PENDING = "pending"
RUNNING = "running"
DONE = "done"
SKIPPED = "skipped"
FAILED = "failed"
CANCELLED = "cancelled"

RATE_WINDOW = 5.0
SAMPLE_EVERY = 0.35


@dataclass
class Job:
    """One file, its destination, and how far along it is."""

    path: str
    rel: str
    url: str
    dest: Path
    size: int | None = None

    done: int = 0
    total: int | None = None
    state: str = PENDING
    error: Text | None = None
    speed: float = 0.0
    resumed_from: int = 0

    mark_at: float = field(default=0.0, repr=False)
    mark_done: int = field(default=0, repr=False)
    prev_done: int = field(default=0, repr=False)

    @property
    def name(self) -> str:
        return self.rel.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Snapshot:
    """What the window draws. A copy, so nothing changes mid-repaint."""

    jobs: tuple[Job, ...] = ()
    running: bool = False
    paused: bool = False
    total_bytes: int = 0
    done_bytes: int = 0
    speed: float = 0.0
    eta: float | None = None
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def fraction(self) -> float:
        return min(1.0, self.done_bytes / self.total_bytes) if self.total_bytes else 0.0


class Manager:
    """Runs a list of `Job`s across a few threads until they are all finished."""

    def __init__(self, token: str = "", threads: int = 3, retries: int = 5) -> None:
        self.token = token
        self.threads = max(1, threads)
        self.retries = retries
        self.events: queue.Queue[Text] = queue.Queue()

        self._lock = threading.Lock()
        self._jobs: list[Job] = []
        self._pending: queue.Queue[Job] = queue.Queue()
        self._control = transfer.Control()
        self._samples: deque[tuple[float, int]] = deque()
        self._moved = 0
        self._last_sample = 0.0
        self._alive = 0
        self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def paused(self) -> bool:
        return self._control.paused

    def start(self, jobs: list[Job]) -> None:
        """Begin. Raises `Failure` before starting anything if the disk is too small."""
        if self.running or not jobs:
            return
        needed = sum(
            max(0, (job.size or 0) - transfer.measure(job.dest, job.size)[0])
            for job in jobs
            if job.size
        )
        transfer.check_space(jobs[0].dest.parent, needed)

        with self._lock:
            self._jobs = jobs
            self._pending = queue.Queue()
            for job in jobs:
                self._pending.put(job)
            self._control = transfer.Control()
            self._samples.clear()
            self._moved = 0
            self._last_sample = 0.0
            self._running = True
            self._alive = min(self.threads, len(jobs))
            workers = [
                threading.Thread(target=self._work, name=f"hfdl-{i + 1}", daemon=True)
                for i in range(self._alive)
            ]
        for worker in workers:
            worker.start()

    def pause(self) -> None:
        self._control.pause()

    def resume(self) -> None:
        self._control.resume()

    def stop(self) -> None:
        self._control.stop()

    def snapshot(self) -> Snapshot:
        with self._lock:
            jobs = tuple(copy.copy(job) for job in self._jobs)
            speed = self._rate()
            running = self._running
        total = sum(job.size or job.total or 0 for job in jobs)
        done = sum(min(job.done, job.size) if job.size else job.done for job in jobs)
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job.state] = counts.get(job.state, 0) + 1
        left = max(0, total - done)
        return Snapshot(
            jobs=jobs,
            running=running,
            paused=self._control.paused,
            total_bytes=total,
            done_bytes=done,
            speed=speed,
            eta=(left / speed) if speed > 0 and left else (0.0 if not left else None),
            counts=counts,
        )

    def _work(self) -> None:
        client = make_client()
        try:
            while True:
                try:
                    job = self._pending.get_nowait()
                except queue.Empty:
                    return
                if self._control.stopped:
                    self._set(job, CANCELLED)
                    continue
                self._run_one(client, job)
        finally:
            client.close()
            self._retire()

    def _run_one(self, client: httpx.Client, job: Job) -> None:
        have, complete = transfer.measure(job.dest, job.size)
        if complete:
            with self._lock:
                job.done = job.size or have
                job.state = SKIPPED
            self.events.put(i18n.MSG_SKIP_FILE.fmt(name=job.name))
            return

        with self._lock:
            job.state = RUNNING
            job.done = job.prev_done = job.mark_done = have
            job.resumed_from = have
            job.mark_at = transfer.now()
        if have:
            self.events.put(i18n.MSG_RESUME_FILE.fmt(name=job.name, size=human_size(have)))

        try:
            transfer.fetch(
                client,
                job.url,
                job.dest,
                token=self.token,
                size=job.size,
                retries=self.retries,
                on_progress=lambda done, total, j=job: self._progress(j, done, total),
                control=self._control,
            )
        except transfer.Cancelled:
            self._set(job, CANCELLED)
            return
        except Failure as exc:
            self._set(job, FAILED, exc.text)
            self.events.put(i18n.MSG_FAIL_FILE.fmt(name=job.name, err=exc.text.en))
            return
        except Exception as exc:
            self._set(job, FAILED, i18n.ERR_NETWORK.fmt(err=exc))
            self.events.put(i18n.MSG_FAIL_FILE.fmt(name=job.name, err=exc))
            return

        with self._lock:
            job.state = DONE
            job.done = job.size or job.done
            job.speed = 0.0
        self.events.put(i18n.MSG_DONE_FILE.fmt(name=job.name))

    def _progress(self, job: Job, done: int, total: int | None) -> None:
        moment = transfer.now()
        with self._lock:
            self._moved += max(0, done - job.prev_done)
            job.prev_done = done
            job.done = done
            if total:
                job.total = total
                if job.size is None:
                    job.size = total

            span = moment - job.mark_at
            if span >= SAMPLE_EVERY:
                instant = max(0, done - job.mark_done) / span
                job.speed = instant if job.speed <= 0 else job.speed * 0.6 + instant * 0.4
                job.mark_at, job.mark_done = moment, done

            if moment - self._last_sample >= SAMPLE_EVERY:
                self._last_sample = moment
                self._samples.append((moment, self._moved))
                while len(self._samples) > 2 and moment - self._samples[0][0] > RATE_WINDOW:
                    self._samples.popleft()

    def _rate(self) -> float:
        """Bytes per second over the sample window. The caller holds the lock."""
        if len(self._samples) < 2:
            return 0.0
        (first_at, first_b), (last_at, last_b) = self._samples[0], self._samples[-1]
        span = last_at - first_at
        return max(0.0, (last_b - first_b) / span) if span > 0 else 0.0

    def _set(self, job: Job, state: str, error: Text | None = None) -> None:
        with self._lock:
            job.state = state
            job.error = error
            job.speed = 0.0

    def _retire(self) -> None:
        """The last worker out reports the tally.

        Counted rather than probed with `is_alive()`: two workers finishing at
        once would each see the other still alive inside its own `finally`, and
        nobody would report.
        """
        with self._lock:
            self._alive -= 1
            if self._alive > 0:
                return
            self._running = False
            self._samples.clear()
            jobs = list(self._jobs)
        if self._control.stopped:
            self.events.put(i18n.MSG_STOPPED)
        self.events.put(
            i18n.MSG_FINISHED.fmt(
                ok=sum(1 for job in jobs if job.state == DONE),
                skip=sum(1 for job in jobs if job.state == SKIPPED),
                fail=sum(1 for job in jobs if job.state in (FAILED, CANCELLED)),
            )
        )
