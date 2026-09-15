"""The window.

Everything slow happens on another thread, and the window learns about it in
exactly two ways: a `Snapshot` it asks the manager for on a 200 ms timer, and a
queue of already-worded messages it drains at the same moment. No worker ever
touches a widget - tkinter is not thread-safe, and the failure mode when it is
touched from a thread is not an exception but a hang, days later, on somebody
else's machine.

Three decisions in the layout are deliberate.

**The check marks are text, not images.** `☑` and `☐` sit in the tree column's
own string, so a click anywhere on the row toggles the file and Space toggles
the selected rows. A Treeview has no checkbox of its own, and the alternative -
generated `PhotoImage` squares - buys nothing but a font question.

**The filter rebuilds the tree instead of hiding rows**, and the tick marks
survive it, because they are kept in a set of paths rather than in the widget.
So `Filter: .safetensors` followed by `Select all` means "select all the
safetensors", which is what a person typing that expects, and clearing the
filter afterwards does not lose the selection.

**The three history boxes are combo boxes, not fields with a button beside
them.** Repository, mirror and save folder are all things whose answer is nearly
always one of the last few, and a file dialog is four clicks to say something
the program already knows. Browse is still there for the first time, and a
right-click drops one entry or the lot - a menu rather than three more buttons
on a window that has enough of them.

Picking a repository out of its history also loads it. The list exists to save
the second step as much as the first, and `<<ComboboxSelected>>` only fires on a
deliberate click, never on browsing the drop-down.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dataclasses import replace

from . import __version__, hub, i18n, manager as mgr, transfer
from .config import MAX_THREADS, Settings
from .fmt import human_eta, human_size, human_speed, percent
from .i18n import Failure, Text

TICK = 200            
CHECKED = "☑ "   
UNCHECKED = "☐ "
PARTIAL = "◼ "   

STATE_TEXT = {
    mgr.PENDING: i18n.ST_PENDING,
    mgr.RUNNING: i18n.ST_RUNNING,
    mgr.DONE: i18n.ST_DONE,
    mgr.SKIPPED: i18n.ST_SKIPPED,
    mgr.FAILED: i18n.ST_FAILED,
    mgr.CANCELLED: i18n.ST_CANCELLED,
}

log = logging.getLogger("hfdl")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.lang = i18n.pick_lang(self.settings.lang)

        self.ref: hub.RepoRef | None = None
        self.files: list[hub.RemoteFile] = []
        self.by_rel: dict[str, hub.RemoteFile] = {}
        self.checked: set[str] = set()
        self.local: dict[str, tuple[int, bool]] = {}
        self.dir_files: dict[str, list[str]] = {}
        self.manager: mgr.Manager | None = None
        self.queue_rows: set[str] = set()

        self._i18n: list[tuple[Any, str, Text]] = []
        self._headings: list[tuple[ttk.Treeview, str, Text]] = []
        self._menu_items: list[tuple[tk.Menu, int, Text]] = []
        self._results: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._last: mgr.Snapshot = mgr.Snapshot()
        self._was_running = False
        self._busy = False

        self.title(f"{i18n.APP_TITLE(self.lang)}  {__version__}")
        self.minsize(1000, 720)
        if self.settings.geometry:
            try:
                self.geometry(self.settings.geometry)
            except tk.TclError:
                pass
        self._build()
        self.retranslate()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(TICK, self._tick)
        self._say(i18n.MSG_READY)
        if not self.settings.verify_ssl:
            self._say(i18n.MSG_NO_VERIFY)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        pad = dict(padx=8, pady=4)

        self._build_source().grid(row=0, column=0, sticky="ew", **pad)
        self._build_target().grid(row=1, column=0, sticky="ew", **pad)

        self.paned = ttk.PanedWindow(self, orient="vertical")
        self.paned.grid(row=2, column=0, sticky="nsew", **pad)
        self.paned.add(self._build_files(self.paned), weight=3)
        self.paned.add(self._build_queue(self.paned), weight=2)
        self.after(80, self._place_sash)

        self._build_actions().grid(row=3, column=0, sticky="ew", **pad)
        self._build_log().grid(row=4, column=0, sticky="ew", **pad)

    def _place_sash(self) -> None:
        try:
            height = self.paned.winfo_height()
            if height > 200:
                self.paned.sashpos(0, int(height * 0.58))
        except tk.TclError:
            pass

    def _build_source(self) -> ttk.Widget:
        box = ttk.LabelFrame(self)
        self._track(box, i18n.SEC_SOURCE)
        box.columnconfigure(1, weight=1)

        self._track(self._label(box, 0, 0), i18n.LBL_REPO)
        self.repo_var = tk.StringVar(value=self.settings.last_repo)
        self.repo_combo = ttk.Combobox(
            box, textvariable=self.repo_var, values=self.settings.recent_repos
        )
        self.repo_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.repo_combo.bind("<Return>", lambda _e: self._fetch())
        self.repo_combo.bind("<<ComboboxSelected>>", lambda _e: self.after_idle(self._fetch))
        self._history_menu(self.repo_combo, "recent_repos")

        self.kind_var = tk.StringVar(value=self.settings.last_repo_type)
        kinds = ttk.Frame(box)
        kinds.grid(row=0, column=2, padx=4)
        for col, (kind, text) in enumerate(
            (("model", i18n.TYPE_MODEL), ("dataset", i18n.TYPE_DATASET), ("space", i18n.TYPE_SPACE))
        ):
            radio = ttk.Radiobutton(kinds, variable=self.kind_var, value=kind)
            radio.grid(row=0, column=col, padx=2)
            self._track(radio, text)

        self._track(self._label(box, 1, 0), i18n.LBL_REVISION)
        line = ttk.Frame(box)
        line.grid(row=1, column=1, sticky="ew", padx=4)
        self.rev_var = tk.StringVar(value="main")
        self.rev_combo = ttk.Combobox(line, textvariable=self.rev_var, width=22, values=["main"])
        self.rev_combo.grid(row=0, column=0, sticky="w", pady=4)

        self._track(self._label(line, 0, 1, padx=(20, 4)), i18n.LBL_ENDPOINT)
        self.endpoint_var = tk.StringVar(
            value=self.settings.endpoint or hub.default_endpoint()
        )
        self.endpoint_combo = ttk.Combobox(
            line, textvariable=self.endpoint_var, width=34, values=self._endpoint_values()
        )
        self.endpoint_combo.grid(row=0, column=2, sticky="w", pady=4)
        self._history_menu(self.endpoint_combo, "recent_endpoints")

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=2, sticky="e", padx=4)
        self.fetch_btn = ttk.Button(buttons, command=self._fetch)
        self.fetch_btn.grid(row=0, column=0, padx=2)
        self._track(self.fetch_btn, i18n.BTN_FETCH)
        self.page_btn = ttk.Button(buttons, command=self._open_page, state="disabled")
        self.page_btn.grid(row=0, column=1, padx=2)
        self._track(self.page_btn, i18n.BTN_OPEN_PAGE)
        self.lang_btn = ttk.Button(buttons, width=5, command=self._switch_lang)
        self.lang_btn.grid(row=0, column=2, padx=(12, 2))
        return box

    def _build_target(self) -> ttk.Widget:
        box = ttk.LabelFrame(self)
        self._track(box, i18n.SEC_TARGET)
        box.columnconfigure(1, weight=1)

        self._track(self._label(box, 0, 0), i18n.LBL_FOLDER)
        self.dest_var = tk.StringVar(value=self.settings.recent_paths[0] if self.settings.recent_paths else "")
        self.dest_combo = ttk.Combobox(box, textvariable=self.dest_var, values=self.settings.recent_paths)
        self.dest_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.dest_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_local())
        self.dest_combo.bind("<FocusOut>", lambda _e: self._refresh_local())
        self.dest_combo.bind("<Return>", lambda _e: self._refresh_local())
        self._history_menu(self.dest_combo, "recent_paths")

        row = ttk.Frame(box)
        row.grid(row=0, column=2, padx=4)
        for col, (text, command) in enumerate(
            ((i18n.BTN_BROWSE, self._browse),
             (i18n.BTN_OPEN_FOLDER, self._open_folder),
             (i18n.BTN_FORGET, self._forget_paths))
        ):
            button = ttk.Button(row, command=command)
            button.grid(row=0, column=col, padx=2)
            self._track(button, text)

        options = ttk.Frame(box)
        options.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(0, 4))

        self.structure_var = tk.BooleanVar(value=self.settings.keep_structure)
        check = ttk.Checkbutton(options, variable=self.structure_var, command=self._refresh_local)
        check.grid(row=0, column=0, sticky="w")
        self._track(check, i18n.CHK_STRUCTURE)

        self._track(self._label(options, 0, 1, padx=(20, 4)), i18n.LBL_THREADS)
        self.threads_var = tk.IntVar(value=self.settings.threads)
        ttk.Spinbox(options, from_=1, to=MAX_THREADS, width=4, textvariable=self.threads_var).grid(
            row=0, column=2, sticky="w"
        )

        self._track(self._label(options, 0, 3, padx=(20, 4)), i18n.LBL_TOKEN)
        self.token_var = tk.StringVar(value=self.settings.token)
        self.token_entry = ttk.Entry(options, textvariable=self.token_var, width=30, show="•")
        self.token_entry.grid(row=0, column=4, sticky="w")
        self.show_token_var = tk.BooleanVar(value=False)
        show = ttk.Checkbutton(options, variable=self.show_token_var, command=self._toggle_token)
        show.grid(row=0, column=5, padx=4)
        self._track(show, i18n.CHK_SHOW_TOKEN)
        self.token_hint = ttk.Label(options, foreground="#666666")
        self.token_hint.grid(row=0, column=6, sticky="w", padx=8)
        self._track(self.token_hint, i18n.HINT_TOKEN)

        self.no_verify_var = tk.BooleanVar(value=not self.settings.verify_ssl)
        insecure = ttk.Checkbutton(options, variable=self.no_verify_var, command=self._toggle_verify)
        insecure.grid(row=1, column=0, columnspan=7, sticky="w", pady=(4, 0))
        self._track(insecure, i18n.CHK_NO_VERIFY)
        return box

    def _build_files(self, parent: ttk.Widget) -> ttk.Widget:
        box = ttk.LabelFrame(parent)
        self._track(box, i18n.SEC_FILES)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)

        bar = ttk.Frame(box)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        for col, (text, command) in enumerate(
            ((i18n.BTN_ALL, lambda: self._bulk("all")),
             (i18n.BTN_NONE, lambda: self._bulk("none")),
             (i18n.BTN_INVERT, lambda: self._bulk("invert")),
             (i18n.BTN_EXPAND, lambda: self._fold(True)),
             (i18n.BTN_COLLAPSE, lambda: self._fold(False)))
        ):
            button = ttk.Button(bar, command=command)
            button.grid(row=0, column=col, padx=2)
            self._track(button, text)

        self._track(self._label(bar, 0, 9, padx=(20, 4)), i18n.LBL_FILTER)
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(bar, textvariable=self.filter_var, width=28)
        filter_entry.grid(row=0, column=10)
        self.filter_var.trace_add("write", lambda *_a: self._rebuild_tree())
        bar.columnconfigure(11, weight=1)
        self.summary = ttk.Label(bar, anchor="e")
        self.summary.grid(row=0, column=11, sticky="ew", padx=8)

        self.tree = ttk.Treeview(box, columns=("size", "local"), show="tree headings", selectmode="extended")
        self.tree.column("#0", width=520, minwidth=240, stretch=True)
        self.tree.column("size", width=110, anchor="e", stretch=False)
        self.tree.column("local", width=140, anchor="center", stretch=False)
        self._heading(self.tree, "#0", i18n.COL_NAME)
        self._heading(self.tree, "size", i18n.COL_SIZE)
        self._heading(self.tree, "local", i18n.COL_LOCAL)
        self.tree.tag_configure("have", foreground="#1a7f37")
        self.tree.tag_configure("part", foreground="#9a6700")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 4), pady=(0, 4))
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)
        return box

    def _build_queue(self, parent: ttk.Widget) -> ttk.Widget:
        box = ttk.LabelFrame(parent)
        self._track(box, i18n.SEC_QUEUE)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        columns = ("done", "size", "speed", "eta", "state")
        self.queue = ttk.Treeview(box, columns=columns, show="tree headings", selectmode="browse")
        self.queue.column("#0", width=420, minwidth=200, stretch=True)
        for name, width in (("done", 90), ("size", 100), ("speed", 100), ("eta", 110), ("state", 130)):
            self.queue.column(name, width=width, anchor="center", stretch=False)
        self._heading(self.queue, "#0", i18n.QCOL_FILE)
        self._heading(self.queue, "done", i18n.QCOL_DONE)
        self._heading(self.queue, "size", i18n.QCOL_SIZE)
        self._heading(self.queue, "speed", i18n.QCOL_SPEED)
        self._heading(self.queue, "eta", i18n.QCOL_ETA)
        self._heading(self.queue, "state", i18n.QCOL_STATE)
        self.queue.tag_configure("done", foreground="#1a7f37")
        self.queue.tag_configure("failed", foreground="#b3261e")
        self.queue.tag_configure("skipped", foreground="#666666")
        self.queue.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=4)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.queue.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=4)
        self.queue.configure(yscrollcommand=scroll.set)
        return box

    def _build_actions(self) -> ttk.Widget:
        box = ttk.Frame(self)
        box.columnconfigure(0, weight=1)

        self.bar = ttk.Progressbar(box, mode="determinate", maximum=1000)
        self.bar.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        self.overall = ttk.Label(box, width=52, anchor="w")
        self.overall.grid(row=0, column=1, sticky="w")

        buttons = ttk.Frame(box)
        buttons.grid(row=0, column=2, sticky="e")
        self.start_btn = ttk.Button(buttons, width=14, command=self._start)
        self.start_btn.grid(row=0, column=0, padx=3)
        self._track(self.start_btn, i18n.BTN_START)
        self.pause_btn = ttk.Button(buttons, width=14, command=self._pause, state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=3)
        self._track(self.pause_btn, i18n.BTN_PAUSE)
        self.stop_btn = ttk.Button(buttons, width=14, command=self._stop, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=3)
        self._track(self.stop_btn, i18n.BTN_STOP)
        return box

    def _build_log(self) -> ttk.Widget:
        box = ttk.LabelFrame(self)
        self._track(box, i18n.SEC_LOG)
        box.columnconfigure(0, weight=1)
        self.log_text = tk.Text(box, height=7, wrap="none", state="disabled",
                                background="#fbfbfb", relief="flat")
        self.log_text.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=4)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=4)
        self.log_text.configure(yscrollcommand=scroll.set)
        return box

    def _label(self, parent: ttk.Widget, row: int, column: int, **grid: Any) -> ttk.Label:
        label = ttk.Label(parent)
        label.grid(row=row, column=column, sticky="w", **{"padx": 4, "pady": 4, **grid})
        return label

    def _track(self, widget: Any, text: Text) -> Any:
        """Remember a widget's caption so the RU/EN button can rewrite it."""
        self._i18n.append((widget, "text", text))
        widget.configure(text=text(self.lang))
        return widget

    def _heading(self, tree: ttk.Treeview, column: str, text: Text) -> None:
        self._headings.append((tree, column, text))
        tree.heading(column, text=text(self.lang))

    def _history_menu(self, widget: ttk.Combobox, attr: str) -> None:
        """Right-click a history box to drop one entry or the lot.

        A menu rather than a button per list: three more buttons on a window
        that already has enough, for something done once in a hundred sessions.
        """
        menu = tk.Menu(widget, tearoff=0)

        def forget_one() -> None:
            value = widget.get().strip()
            kept = [i for i in getattr(self.settings, attr) if i.lower() != value.lower()]
            setattr(self.settings, attr, kept)
            self._refresh_history()

        def forget_all() -> None:
            setattr(self.settings, attr, [])
            self._refresh_history()

        for index, (text, command) in enumerate(
            ((i18n.MENU_FORGET_ONE, forget_one), (i18n.MENU_FORGET_ALL, forget_all))
        ):
            menu.add_command(label=text(self.lang), command=command)
            self._menu_items.append((menu, index, text))

        def popup(event: tk.Event) -> None:
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", popup)

    def _refresh_history(self) -> None:
        """Re-fill every history drop-down from the settings, and write them out."""
        self.repo_combo.configure(values=self.settings.recent_repos)
        self.endpoint_combo.configure(values=self._endpoint_values())
        self.dest_combo.configure(values=self.settings.recent_paths)
        self.settings.save()

    def retranslate(self) -> None:
        for widget, option, text in self._i18n:
            try:
                widget.configure(**{option: text(self.lang)})
            except tk.TclError:
                pass
        for tree, column, text in self._headings:
            tree.heading(column, text=text(self.lang))
        for menu, index, text in self._menu_items:
            menu.entryconfigure(index, label=text(self.lang))
        self.title(f"{i18n.APP_TITLE(self.lang)}  {__version__}")
        self.lang_btn.configure(text="RU" if self.lang == "en" else "EN")
        self._pause_caption()
        self._refresh_local()
        self._refresh_summary()
        self._paint(self._last)

    def _switch_lang(self) -> None:
        self.lang = "ru" if self.lang == "en" else "en"
        self.settings.lang = self.lang
        self.settings.save()
        self.retranslate()
        self._say(i18n.MSG_LANG_SWITCHED)

    def _endpoint_values(self) -> list[str]:
        """The mirror drop-down: the ones everybody uses, then the ones you have."""
        seen: set[str] = set()
        out: list[str] = []
        for url in list(hub.KNOWN_ENDPOINTS) + self.settings.recent_endpoints:
            if url.lower() not in seen:
                seen.add(url.lower())
                out.append(url)
        return out

    def _fetch(self) -> None:
        if self._busy:
            return
        try:
            endpoint = hub.normalise_endpoint(self.endpoint_var.get())
            ref = hub.parse_ref(self.repo_var.get(), self.kind_var.get(), endpoint)
        except Failure as exc:
            self._fail(exc.text)
            return
        self.endpoint_var.set(endpoint)
        revision = self.rev_var.get().strip()
        if (
            ref.revision == ref.default_revision
            and revision
            and revision != ref.revision
            and not self._left_over_default(ref, revision)
        ):
            ref = replace(ref, revision=revision)

        self._busy = True
        self.fetch_btn.configure(state="disabled")
        if ref.modelscope:
            self._say(i18n.MSG_MODELSCOPE.fmt(url=ref.endpoint))
        elif ref.mirrored:
            self._say(i18n.MSG_MIRROR.fmt(url=ref.endpoint))
        self._say(i18n.MSG_FETCHING.fmt(repo=ref))
        token = self.token_var.get().strip()
        verify = self.settings.verify_ssl
        threading.Thread(target=self._fetch_worker, args=(ref, token, verify), daemon=True).start()

    def _left_over_default(self, ref: hub.RepoRef, revision: str) -> bool:
        """A `main` still in the branch box from Hugging Face is not a choice.

        Hugging Face and ModelScope name their default branch differently, so
        after switching between them the box holds the other one's default -
        which, applied, would ask ModelScope for a `main` it does not have.
        """
        switched = self.ref is None or self.ref.modelscope != ref.modelscope
        return switched and revision in (hub.HF_REVISION, hub.MS_REVISION)

    def _fetch_worker(self, ref: hub.RepoRef, token: str, verify: bool) -> None:
        client = hub.make_client(verify=verify)
        try:
            files = hub.list_files(client, ref, token)
            revisions = hub.list_revisions(client, ref, token)
            self._results.put(("files", (ref, files, revisions)))
        except Failure as exc:
            self._results.put(("error", exc.text))
        except Exception as exc:
            self._results.put(("error", i18n.ERR_NETWORK.fmt(err=exc)))
        finally:
            client.close()

    def _on_files(self, ref: hub.RepoRef, files: list[hub.RemoteFile], revisions: list[str]) -> None:
        self.ref = ref
        self.files = files
        self.by_rel = {hub.relative_path(ref, f.path): f for f in files}
        self.checked.clear()
        self.kind_var.set(ref.kind)
        self.rev_combo.configure(values=revisions)
        self.rev_var.set(ref.revision)
        self.page_btn.configure(state="normal")
        self.repo_var.set(ref.slug)
        self.settings.last_repo = ref.slug
        self.settings.last_repo_type = ref.kind
        self.settings.endpoint = ref.endpoint
        self.settings.remember_repo(ref.slug)
        self.settings.remember_endpoint(ref.endpoint)
        self._refresh_history()

        if not self.dest_var.get().strip() and self.settings.recent_paths:
            self.dest_var.set(self.settings.recent_paths[0])

        self._refresh_local()
        self._rebuild_tree()
        if files:
            self._say(i18n.MSG_FETCHED.fmt(
                repo=ref, n=len(files), size=human_size(sum(f.size or 0 for f in files))
            ))
        else:
            self._say(i18n.MSG_NO_FILES)

    def _open_page(self) -> None:
        if self.ref:
            webbrowser.open(self.ref.page_url)

    def _matches(self, rel: str) -> bool:
        pattern = self.filter_var.get().strip().lower()
        if not pattern:
            return True
        target = rel.lower()
        if any(ch in pattern for ch in "*?["):
            return fnmatch(target, pattern) or fnmatch(target.rsplit("/", 1)[-1], pattern)
        return pattern in target

    def _visible(self) -> list[str]:
        return [rel for rel in self.by_rel if self._matches(rel)]

    def _rebuild_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.dir_files = {}
        folders: set[str] = set()

        for rel in sorted(self._visible(), key=lambda r: (r.count("/"), r.lower())):
            parent = ""
            walked = ""
            *dirs, _name = rel.split("/")
            for part in dirs:
                walked = f"{walked}/{part}" if walked else part
                iid = "d:" + walked
                if iid not in folders:
                    folders.add(iid)
                    self.dir_files[iid] = []
                    self.tree.insert(parent, "end", iid=iid, text=UNCHECKED + part, open=True)
                self.dir_files[iid].append(rel)
                parent = iid
            self.tree.insert(parent, "end", iid="f:" + rel, text="", values=("", ""))

        self._refresh_marks()

    def _refresh_marks(self) -> None:
        """Redraw every tick mark, size and disk status from the model."""
        for iid in self._all_nodes():
            if iid.startswith("f:"):
                rel = iid[2:]
                remote = self.by_rel.get(rel)
                mark = CHECKED if rel in self.checked else UNCHECKED
                self.tree.item(iid, text=mark + rel.rsplit("/", 1)[-1])
                have, complete = self.local.get(rel, (0, False))
                size = remote.size if remote else None
                if complete:
                    status, tag = i18n.STAT_HAVE(self.lang), "have"
                elif have and size:
                    status, tag = i18n.STAT_PART.fmt(pct=percent(have, size))(self.lang), "part"
                elif have:
                    status, tag = i18n.STAT_DIFF(self.lang), "part"
                else:
                    status, tag = "", ""
                self.tree.item(iid, values=(human_size(size), status), tags=(tag,) if tag else ())
            else:
                inside = self.dir_files.get(iid, [])
                hit = sum(1 for rel in inside if rel in self.checked)
                mark = CHECKED if hit == len(inside) and inside else (UNCHECKED if not hit else PARTIAL)
                name = iid[2:].rsplit("/", 1)[-1]
                total = sum(self.by_rel[r].size or 0 for r in inside if r in self.by_rel)
                self.tree.item(iid, text=mark + name, values=(human_size(total), ""))
        self._refresh_summary()

    def _all_nodes(self, parent: str = "") -> list[str]:
        found: list[str] = []
        for iid in self.tree.get_children(parent):
            found.append(iid)
            found.extend(self._all_nodes(iid))
        return found

    def _on_tree_click(self, event: tk.Event) -> None:
        if self.tree.identify_element(event.x, event.y) == "Treeitem.indicator":
            return
        if self.tree.identify_region(event.x, event.y) != "tree":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle(iid)

    def _on_tree_space(self, _event: tk.Event) -> str:
        for iid in self.tree.selection():
            self._toggle(iid, refresh=False)
        self._refresh_marks()
        return "break"

    def _toggle(self, iid: str, refresh: bool = True) -> None:
        if iid.startswith("f:"):
            rel = iid[2:]
            if rel in self.checked:
                self.checked.discard(rel)
            else:
                self.checked.add(rel)
        else:
            inside = self.dir_files.get(iid, [])
            if inside and all(rel in self.checked for rel in inside):
                self.checked.difference_update(inside)
            else:
                self.checked.update(inside)
        if refresh:
            self._refresh_marks()

    def _bulk(self, what: str) -> None:
        visible = set(self._visible())
        if what == "all":
            self.checked |= visible
        elif what == "none":
            self.checked -= visible
        else:
            self.checked ^= visible
        self._refresh_marks()

    def _fold(self, open_: bool) -> None:
        for iid in self._all_nodes():
            if iid.startswith("d:"):
                self.tree.item(iid, open=open_)

    def _refresh_summary(self) -> None:
        if not self.by_rel:
            self.summary.configure(text=i18n.SUMMARY_EMPTY(self.lang))
            return
        size = sum(self.by_rel[rel].size or 0 for rel in self.checked if rel in self.by_rel)
        self.summary.configure(text=i18n.SUMMARY.fmt(
            sel=len(self.checked), total=len(self.by_rel), size=human_size(size)
        )(self.lang))

    def _base_dir(self) -> Path | None:
        text = self.dest_var.get().strip().strip('"')
        return Path(text) if text else None

    def _save_rel(self, rel: str) -> str:
        return rel if self.structure_var.get() else rel.rsplit("/", 1)[-1]

    def _refresh_local(self) -> None:
        """Recompute the "On disk" column. Cheap: one stat per file."""
        base = self._base_dir()
        self.local = {}
        if base and self.by_rel:
            for rel, remote in self.by_rel.items():
                try:
                    dest = transfer.safe_destination(base, self._save_rel(rel))
                except Failure:
                    continue
                try:
                    self.local[rel] = transfer.measure(dest, remote.size)
                except OSError:
                    pass
        if getattr(self, "tree", None) and self.tree.get_children():
            self._refresh_marks()

    def _browse(self) -> None:
        start = self.dest_var.get().strip() or (self.settings.recent_paths[0] if self.settings.recent_paths else "")
        chosen = filedialog.askdirectory(
            title=i18n.TITLE_CHOOSE_FOLDER(self.lang),
            initialdir=start or os.path.expanduser("~"),
            mustexist=False,
        )
        if chosen:
            self.dest_var.set(str(Path(chosen)))
            self._refresh_local()

    def _open_folder(self) -> None:
        base = self._base_dir()
        if not base or not base.exists():
            return
        opener = {"win32": None, "darwin": "open"}.get(sys.platform, "xdg-open")
        try:
            if opener is None:
                os.startfile(base)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([opener, str(base)])
        except OSError as exc:
            log.info("could not open %s: %s", base, exc)

    def _forget_paths(self) -> None:
        self.settings.forget_paths()
        self._refresh_history()

    def _toggle_token(self) -> None:
        self.token_entry.configure(show="" if self.show_token_var.get() else "•")

    def _toggle_verify(self) -> None:
        """Saved at once: it decides whether the next request gets anywhere at all.

        A queue that is already running keeps the clients it started with; the
        box applies to the next list load and the next Download press.
        """
        self.settings.verify_ssl = not self.no_verify_var.get()
        self.settings.save()
        if not self.settings.verify_ssl:
            self._say(i18n.MSG_NO_VERIFY)

    def _start(self) -> None:
        if self.manager and self.manager.running:
            return
        if not self.ref or not self.by_rel:
            self._fail(i18n.ERR_NO_REPO)
            return
        if not self.checked:
            self._fail(i18n.ERR_NO_SELECTION)
            return
        base = self._base_dir()
        if base is None:
            self._fail(i18n.ERR_NO_FOLDER)
            return
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._fail(i18n.ERR_BAD_FOLDER.fmt(folder=base, err=exc))
            return

        try:
            jobs = self._jobs(base)
        except Failure as exc:
            self._fail(exc.text)
            return

        self.settings.remember_path(str(base))
        self.settings.threads = max(1, min(MAX_THREADS, int(self.threads_var.get() or 3)))
        self.settings.keep_structure = self.structure_var.get()
        self.settings.token = self.token_var.get().strip()
        self._refresh_history()

        self.manager = mgr.Manager(
            token=hub.token_for(self.ref, self.settings.token),
            threads=self.settings.threads,
            verify=self.settings.verify_ssl,
        )
        try:
            self.manager.start(jobs)
        except Failure as exc:
            self._fail(exc.text)
            return

        self._fill_queue(jobs)
        self._say(i18n.MSG_START.fmt(
            n=len(jobs), size=human_size(sum(j.size or 0 for j in jobs))
        ))
        self._buttons(running=True)

    def _jobs(self, base: Path) -> list[mgr.Job]:
        """Turn the tick marks into a work list.

        Flattening can make two files fight over one name (`config.json` in two
        subfolders); those keep their subfolder rather than silently overwriting
        each other, and the log says so.
        """
        assert self.ref is not None
        chosen = sorted(rel for rel in self.checked if rel in self.by_rel)
        flat = not self.structure_var.get()
        clashes: set[str] = set()
        if flat:
            seen: dict[str, str] = {}
            for rel in chosen:
                name = rel.rsplit("/", 1)[-1].lower()
                if name in seen:
                    clashes.update((rel, seen[name]))
                seen[name] = rel
            if clashes:
                self._say(i18n.WARN_FLAT_CLASH.fmt(n=len(clashes)))

        jobs = []
        for rel in chosen:
            remote = self.by_rel[rel]
            save_as = rel if (not flat or rel in clashes) else rel.rsplit("/", 1)[-1]
            jobs.append(mgr.Job(
                path=remote.path,
                rel=save_as,
                url=hub.download_url(self.ref, remote.path),
                dest=transfer.safe_destination(base, save_as),
                size=remote.size,
            ))
        return jobs

    def _pause(self) -> None:
        if not self.manager or not self.manager.running:
            return
        if self.manager.paused:
            self.manager.resume()
            self._say(i18n.MSG_RESUMED)
        else:
            self.manager.pause()
            self._say(i18n.MSG_PAUSED)
        self._pause_caption()

    def _pause_caption(self) -> None:
        paused = bool(self.manager and self.manager.paused)
        text = i18n.BTN_RESUME if paused else i18n.BTN_PAUSE
        self.pause_btn.configure(text=text(self.lang))
        for index, (widget, option, _old) in enumerate(self._i18n):
            if widget is self.pause_btn and option == "text":
                self._i18n[index] = (widget, option, text)

    def _stop(self) -> None:
        if self.manager:
            self.manager.stop()
            self.stop_btn.configure(state="disabled")

    def _buttons(self, running: bool) -> None:
        self.start_btn.configure(state="disabled" if running else "normal")
        self.pause_btn.configure(state="normal" if running else "disabled")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.fetch_btn.configure(state="disabled" if running or self._busy else "normal")

    def _fill_queue(self, jobs: list[mgr.Job]) -> None:
        self.queue.delete(*self.queue.get_children())
        self.queue_rows = set()
        for job in jobs:
            self.queue.insert("", "end", iid=job.rel, text=job.rel,
                              values=("", human_size(job.size), "", "", i18n.ST_PENDING(self.lang)))
            self.queue_rows.add(job.rel)

    def _paint(self, snap: mgr.Snapshot) -> None:
        self._last = snap
        for job in snap.jobs:
            if job.rel not in self.queue_rows:
                continue
            state = STATE_TEXT.get(job.state, i18n.ST_PENDING)
            if job.state == mgr.RUNNING and snap.paused:
                state = i18n.ST_PAUSED
            eta = ""
            if job.state == mgr.RUNNING and job.speed > 0 and job.size:
                eta = human_eta(max(0, job.size - job.done) / job.speed, self.lang)
            tag = {mgr.DONE: "done", mgr.SKIPPED: "skipped",
                   mgr.FAILED: "failed", mgr.CANCELLED: "failed"}.get(job.state, "")
            self.queue.item(job.rel, values=(
                percent(job.done, job.size or job.total),
                human_size(job.size or job.total),
                human_speed(job.speed) if job.state == mgr.RUNNING else "",
                eta,
                state(self.lang) if not job.error else f"{state(self.lang)}: {job.error(self.lang)}",
            ), tags=(tag,) if tag else ())

        self.bar.configure(value=snap.fraction * 1000)
        if not snap.jobs:
            self.overall.configure(text=i18n.OVERALL_IDLE(self.lang))
        elif snap.paused:
            self.overall.configure(text=i18n.OVERALL_PAUSED.fmt(
                done=human_size(snap.done_bytes), total=human_size(snap.total_bytes)
            )(self.lang))
        else:
            self.overall.configure(text=i18n.OVERALL.fmt(
                done=human_size(snap.done_bytes),
                total=human_size(snap.total_bytes),
                speed=human_speed(snap.speed),
                eta=human_eta(snap.eta, self.lang),
            )(self.lang))

    def _tick(self) -> None:
        try:
            while True:
                kind, payload = self._results.get_nowait()
                if kind == "files":
                    self._busy = False
                    self._on_files(*payload)
                elif kind == "error":
                    self._busy = False
                    self._fail(payload)
                self._buttons(running=bool(self.manager and self.manager.running))
        except queue.Empty:
            pass

        if self.manager:
            try:
                while True:
                    self._say(self.manager.events.get_nowait())
            except queue.Empty:
                pass
            running = self.manager.running
            self._paint(self.manager.snapshot())
            if self._was_running and not running:
                self._buttons(running=False)
                self._pause_caption()
                self._refresh_local()
            self._was_running = running

        self.after(TICK, self._tick)

    def _say(self, text: Text) -> None:
        log.info(text.en)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text(self.lang) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _fail(self, text: Text) -> None:
        self._say(text)
        messagebox.showerror(i18n.APP_TITLE(self.lang), text(self.lang), parent=self)

    def _on_close(self) -> None:
        if self.manager and self.manager.running:
            if not messagebox.askyesno(
                i18n.ASK_CLOSE_TITLE(self.lang), i18n.ASK_CLOSE(self.lang), parent=self
            ):
                return
            self.manager.stop()
        self.settings.geometry = self.winfo_geometry()
        self.settings.threads = max(1, min(MAX_THREADS, int(self.threads_var.get() or 3)))
        self.settings.keep_structure = self.structure_var.get()
        self.settings.token = self.token_var.get().strip()
        self.settings.last_repo = self.repo_var.get().strip()
        self.settings.lang = self.lang
        try:
            self.settings.endpoint = hub.normalise_endpoint(self.endpoint_var.get())
        except Failure:
            pass
        self.settings.save()
        self.destroy()


def _setup_logging() -> None:
    from .config import LOG_PATH

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def _dpi() -> None:
    """Ask Windows for real pixels; without this the window is a blurred bitmap."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        pass


def main() -> int:
    _setup_logging()
    log.info("hf-simple-downloader %s", __version__)
    _dpi()
    app = App()
    try:
        style = ttk.Style(app)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    app.mainloop()
    return 0
