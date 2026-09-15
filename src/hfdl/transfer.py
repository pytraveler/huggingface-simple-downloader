"""Moving one file from the Hub onto the disk, and picking it up where it stopped.

Adapted from the async downloader in comfyui-mcp; the shape is the same and so
are the three facts it was built around.

**The token never goes past the first host.** A `resolve` URL answers 302 with a
pre-signed CDN link, and an `Authorization` header on that hop is a 400. So
redirects are walked by hand and credentials are attached only to huggingface.co.

**A signed link expires.** Every retry re-walks from the original URL instead of
reusing the resolved one, or a resume an hour later fetches an XML error page and
writes it into the middle of a model.

**A half-written file must not look finished.** Bytes go to `<name>.part` and are
moved into place only when the whole file is there; the rename is atomic within
the directory. That `.part` is also what makes resuming work - it is the record
of how far the last attempt got, and it is deliberately left behind when a
transfer is stopped.

`Control` is the fourth thing, and it is new here: a window has a Pause button
and a Stop button, so the chunk loop checks between blocks. Pausing holds the
connection open, which a CDN will eventually drop - and that is fine, because a
dropped connection is a retry and a retry is a resume.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from . import i18n
from .fmt import human_size
from .hub import USER_AGENT, is_modelscope
from .i18n import Failure

MAX_HOPS = 10
CHUNK = 1 << 20
BACKOFF_CAP = 30.0
REDIRECTS = (301, 302, 303, 307, 308)
RETRY_STATUS = (408, 425, 429, 500, 502, 503, 504)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SPACE_MARGIN = 1.02

ProgressFn = Callable[[int, "int | None"], None]


class Cancelled(Exception):
    """The user pressed Stop. Not an error, and not worth a message."""


class Control:
    """The Pause and Stop buttons, as the worker threads see them.

    One of these is shared by every worker in a run: pausing pauses all of them,
    and stopping stops all of them, which is what the two buttons say they do.
    """

    def __init__(self) -> None:
        self._go = threading.Event()
        self._go.set()
        self._stop = threading.Event()

    def pause(self) -> None:
        self._go.clear()

    def resume(self) -> None:
        self._go.set()

    def stop(self) -> None:
        self._stop.set()
        self._go.set()

    @property
    def paused(self) -> bool:
        return not self._go.is_set() and not self._stop.is_set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def checkpoint(self) -> None:
        """Called between chunks: parks while paused, raises once stopped."""
        if self._stop.is_set():
            raise Cancelled()
        if not self._go.is_set():
            self._go.wait()
            if self._stop.is_set():
                raise Cancelled()

    def sleep(self, seconds: float) -> None:
        """A backoff that Stop can cut short."""
        if self._stop.wait(seconds):
            raise Cancelled()


def safe_destination(base: Path, relative: str) -> Path:
    """`base / relative`, or a refusal if that leaves `base`.

    Repository paths come off the network, and a path is the one field where
    "it came from a trusted API" is not an argument worth making.
    """
    cleaned = relative.replace("\\", "/").strip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise Failure(i18n.ERR_UNSAFE_NAME.fmt(name=relative))
    path = base.joinpath(*parts)
    try:
        resolved, root = path.resolve(), base.resolve()
    except OSError:
        resolved, root = path.absolute(), base.absolute()
    if resolved != root and root not in resolved.parents:
        raise Failure(i18n.ERR_UNSAFE_NAME.fmt(name=relative))
    return path


def free_space(directory: Path) -> int:
    """Bytes free on the volume holding `directory`, or its nearest existing parent."""
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def check_space(directory: Path, needed: int | None) -> None:
    """Refuse up front rather than filling the volume and failing at 99%."""
    if not needed:
        return
    free = free_space(directory)
    if free < needed * SPACE_MARGIN:
        raise Failure(
            i18n.ERR_SPACE.fmt(
                need=human_size(needed),
                drive=directory.anchor or str(directory),
                free=human_size(free),
            )
        )


@dataclass
class Preflight:
    url: str
    final_url: str
    size: int | None = None
    sha256: str = ""
    resumable: bool = False


def _headers(url: str, origin: str, token: str) -> dict[str, str]:
    head = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if token and (urlparse(url).hostname or "").lower() == origin:
        head["Authorization"] = f"Bearer {token.strip()}"
    return head


def _sha256_of(resp: httpx.Response) -> str:
    """The sha256 when the Hub volunteers one. Reported, never enforced."""
    for key in ("x-linked-etag", "etag"):
        raw = (resp.headers.get(key) or "").strip('"W/ ')
        if HEX64.match(raw.lower()):
            return raw.lower()
    return ""


def _size_of(resp: httpx.Response) -> int | None:
    raw = resp.headers.get("x-linked-size")
    if raw and raw.isdigit():
        return int(raw)
    span = (resp.headers.get("content-range") or "").rsplit("/", 1)
    if len(span) == 2 and span[1].strip().isdigit():
        return int(span[1].strip())
    raw = resp.headers.get("content-length")
    return int(raw) if raw and raw.isdigit() and resp.status_code == 200 else None


def _hop(client: httpx.Client, url: str, head: dict[str, str]) -> httpx.Response:
    """One request that reads headers only, however the server prefers to allow it."""
    resp = client.request("HEAD", url, headers=head, follow_redirects=False)
    if resp.status_code in (403, 405, 501):
        ranged = dict(head, Range="bytes=0-0")
        resp = client.request("GET", url, headers=ranged, follow_redirects=False)
        resp.close()
    return resp


def preflight(client: httpx.Client, url: str, token: str = "") -> Preflight:
    """Walk the redirects by hand and report what is on the other end."""
    parsed = urlparse(url)
    origin = (parsed.hostname or "").lower()
    if not origin or parsed.scheme not in ("http", "https"):
        raise Failure(i18n.ERR_NOT_URL.fmt(url=url))

    current = url
    size: int | None = None
    sha = ""
    for _ in range(MAX_HOPS):
        resp = _hop(client, current, _headers(current, origin, token))
        size = size if size is not None else _size_of(resp)
        sha = sha or _sha256_of(resp)
        if resp.status_code in REDIRECTS and resp.headers.get("location"):
            current = str(httpx.URL(current).join(resp.headers["location"]))
            continue
        if resp.status_code >= 400:
            raise Failure(_explain(resp.status_code, current))
        return Preflight(
            url=url,
            final_url=current,
            size=size,
            sha256=sha,
            resumable=(resp.headers.get("accept-ranges") or "").lower() == "bytes"
            or resp.status_code == 206,
        )
    raise Failure(i18n.ERR_REDIRECTS.fmt(n=MAX_HOPS, url=url))


def _explain(status: int, url: str) -> i18n.Text:
    """A status code, worded for the person reading the log rather than the wire.

    The repository name is cut back out of the URL: by this point the caller is
    a worker thread that only knows a link, and "Qwen/Qwen3-8B is gated" is a
    sentence somebody can act on where a 403 and a CDN URL are not.
    """
    modelscope = is_modelscope(url)
    if status in (401, 403):
        wording = i18n.ERR_MS_PRIVATE if modelscope else i18n.ERR_GATED
        return wording.fmt(repo=_repo_from(url) or url)
    if status == 404:
        wording = i18n.ERR_MS_NOT_FOUND if modelscope else i18n.ERR_NOT_FOUND
        return wording.fmt(repo=_repo_from(url) or url)
    return i18n.ERR_HTTP.fmt(status=status, url=url)


def _repo_from(url: str) -> str:
    """`.../owner/name/resolve/main/file` -> `owner/name`, or '' off-site.

    ModelScope's dataset links are `/api/v1/datasets/owner/name/repo?...`, and
    its model links carry a `models/` in front; both come back as `owner/name`.
    """
    parts = [p for p in urlparse(url).path.split("/") if p]
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
        if "repo" in parts:
            parts = parts[: parts.index("repo")]
    elif "resolve" in parts:
        parts = parts[: parts.index("resolve")]
    if parts and parts[0] in ("datasets", "spaces", "models"):
        parts = parts[1:]
    return "/".join(parts[:2])


@dataclass
class Transfer:
    path: Path
    size: int
    resumed_from: int
    attempts: int
    sha256: str = ""


def part_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".part")


def _pause_for(attempt: int) -> float:
    """Backoff between attempts. Named so a test need not wait it out."""
    return min(2.0**attempt, BACKOFF_CAP)


def fetch(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    token: str = "",
    size: int | None = None,
    retries: int = 5,
    on_progress: ProgressFn | None = None,
    control: Control | None = None,
    chunk: int = CHUNK,
) -> Transfer:
    """Download `url` to `destination`, carrying on from a previous attempt."""
    control = control or Control()
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = part_path(destination)
    started_at = part.stat().st_size if part.is_file() else 0
    last: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        control.checkpoint()
        have = part.stat().st_size if part.is_file() else 0
        if size is not None and have >= size:
            have = 0
        try:
            written, sha = _attempt(client, url, part, have, size, token, chunk, on_progress, control)
            if size is not None and written != size:
                raise Failure(i18n.ERR_SIZE.fmt(want=size, got=written))
            os.replace(part, destination)
            return Transfer(
                path=destination,
                size=written,
                resumed_from=started_at,
                attempts=attempt,
                sha256=sha,
            )
        except (Failure, Cancelled):
            raise
        except (httpx.HTTPError, OSError) as exc:
            last = exc
            if attempt >= max(1, retries):
                break
            control.sleep(_pause_for(attempt))

    raise Failure(i18n.ERR_GAVE_UP.fmt(n=max(1, retries), err=last))


def _attempt(
    client: httpx.Client,
    url: str,
    part: Path,
    have: int,
    size: int | None,
    token: str,
    chunk: int,
    on_progress: ProgressFn | None,
    control: Control,
) -> tuple[int, str]:
    """One GET, redirects walked by hand here too.

    `preflight` has usually resolved the CDN link already, but not always:
    ModelScope answers HEAD on `resolve` with a plain 200 and only redirects a
    GET. Without this loop the 302's own little HTML body would be written into
    the `.part` as if it were the file.
    """
    plan = preflight(client, url, token)
    origin = (urlparse(url).hostname or "").lower()
    current = plan.final_url

    for _ in range(MAX_HOPS):
        head = _headers(current, origin, token)
        if have:
            head["Range"] = f"bytes={have}-"
        with client.stream("GET", current, headers=head, follow_redirects=False) as resp:
            if resp.status_code in REDIRECTS and resp.headers.get("location"):
                current = str(httpx.URL(current).join(resp.headers["location"]))
                continue
            if resp.status_code >= 400:
                if resp.status_code in RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                raise Failure(_explain(resp.status_code, current))
            if have and resp.status_code != 206:
                have = 0
            total = size or plan.size or _total_from(resp, have)

            done = have
            if on_progress is not None:
                on_progress(done, total)
            with open(part, "r+b" if have else "wb") as fh:
                if have:
                    fh.seek(have)
                    fh.truncate()
                for block in resp.iter_bytes(chunk):
                    control.checkpoint()
                    fh.write(block)
                    done += len(block)
                    if on_progress is not None:
                        on_progress(done, total)
        return done, plan.sha256
    raise Failure(i18n.ERR_REDIRECTS.fmt(n=MAX_HOPS, url=url))


def _total_from(resp: httpx.Response, have: int) -> int | None:
    """The full size out of a partial response: content-length is only the rest."""
    span = resp.headers.get("content-range") or ""
    if "/" in span:
        tail = span.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            return int(tail)
    length = resp.headers.get("content-length")
    return have + int(length) if length and length.isdigit() else None


def measure(destination: Path, size: int | None) -> tuple[int, bool]:
    """How much of this file is already on disk, and whether it is finished.

    Answers the "On disk" column as well as the queue's skip decision, so the
    window can say what a Download press is about to do before it does it.
    """
    if destination.is_file():
        have = destination.stat().st_size
        if size is None or have == size:
            return have, True
        return have, False
    part = part_path(destination)
    if part.is_file():
        return part.stat().st_size, False
    return 0, False


def now() -> float:
    """Monotonic clock, in one place so speed maths cannot pick a wall clock."""
    return time.monotonic()
