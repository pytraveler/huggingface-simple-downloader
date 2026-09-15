"""What the window remembers between runs.

One JSON file next to the launcher, so the whole thing stays portable: copy the
folder to another machine and the list of save folders comes along. Nothing here
is required - a missing or broken file is the same as a fresh install, because a
settings file is not worth a startup failure.

The token is stored in clear text. That is stated in the README rather than
hidden: a Hugging Face read token is not a password, the alternative on Windows
is DPAPI (which would tie the file to one user account and defeat the portable
copy), and a user who does not want it on disk can leave the field empty and
paste it per session.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_RECENT = 12
DEFAULT_THREADS = 3
MAX_THREADS = 8


def _launcher_dir() -> Path:
    """The folder the program was started from.

    The project folder when run from source. In the PyInstaller exe `__file__`
    points into the temporary folder the exe unpacks itself to and deletes on
    exit, so settings kept there would be forgotten every run; the exe's own
    folder is the one the user can see.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _root() -> Path:
    """The folder the settings file lives in.

    Next to the launcher (or the exe) normally; `%LOCALAPPDATA%` if that folder
    turns out to be read-only, which happens when the program is unpacked into
    `Program Files` or run off a write-protected share.
    """
    here = _launcher_dir()
    probe = here / ".hfdl-write-test"
    try:
        probe.touch()
        probe.unlink()
        return here
    except OSError:
        fallback = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hf-simple-downloader"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


ROOT = _root()
SETTINGS_PATH = ROOT / "settings.json"
LOG_PATH = ROOT / "downloader.log"


@dataclass
class Settings:
    lang: str = ""                     
    token: str = ""
    threads: int = DEFAULT_THREADS
    keep_structure: bool = True
    verify_ssl: bool = True
    last_repo: str = ""
    last_repo_type: str = "model"
    endpoint: str = ""                  
    recent_paths: list[str] = field(default_factory=list)
    recent_repos: list[str] = field(default_factory=list)
    recent_endpoints: list[str] = field(default_factory=list)
    geometry: str = ""

    @staticmethod
    def _remember(items: list[str], value: str) -> list[str]:
        keep = [item for item in items if item.lower() != value.lower()]
        return [value] + keep[: MAX_RECENT - 1]

    def remember_path(self, path: str) -> None:
        self.recent_paths = self._remember(self.recent_paths, str(Path(path)))

    def forget_paths(self) -> None:
        self.recent_paths = []

    def remember_endpoint(self, endpoint: str) -> None:
        self.recent_endpoints = self._remember(self.recent_endpoints, endpoint)

    def remember_repo(self, slug: str) -> None:
        self.recent_repos = self._remember(self.recent_repos, slug)

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        known = {f for f in cls().__dict__}
        clean = {k: v for k, v in raw.items() if k in known}
        try:
            settings = cls(**clean)
        except TypeError:
            return cls()
        settings.threads = max(1, min(MAX_THREADS, int(settings.threads or DEFAULT_THREADS)))
        settings.lang = settings.lang if settings.lang in ("en", "ru") else ""
        settings.verify_ssl = settings.verify_ssl is not False
        settings.recent_paths = [str(p) for p in settings.recent_paths][:MAX_RECENT]
        settings.recent_repos = [str(r) for r in settings.recent_repos][:MAX_RECENT]
        settings.recent_endpoints = [str(e) for e in settings.recent_endpoints][:MAX_RECENT]
        return settings

    def save(self) -> None:
        try:
            SETTINGS_PATH.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
