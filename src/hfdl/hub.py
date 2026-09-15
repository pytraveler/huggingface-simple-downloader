"""Reading a Hugging Face repository: what is in it, and where each file lives.

Two things this module exists to absorb.

**People paste whatever they were looking at.** `Qwen/Qwen3-8B`, the address bar
of the repository page, a link to one file deep in a subfolder, a `datasets/`
page, a `?download=true` link out of somebody's README. All of those name a
repository and most of them also name a branch and a folder, so `parse_ref`
takes the lot and answers with the same four fields. Getting this wrong is the
difference between a file list and an error message, and it is the very first
thing the program does.

**The file list is paginated and the sizes are not where you would look.** The
tree endpoint answers 1000 entries at a time and points at the next page through
a `Link` header, and for an LFS file - which is every file anyone comes here
for - `size` at the top level is the size of the *pointer*, a few hundred bytes.
The real number is `lfs.size`. Reading the wrong one makes a 16 GB model look
like a 134-byte text file, and the progress bar and the free-space check would
both be built on it.

**The Hub is not always at huggingface.co.** A mirror answers the same API at
another host, so the host is not a constant - it rides on the `RepoRef` and
every URL is built from that. It is a setting rather than something inferred
from a pasted link, and that is a deliberate refusal: whatever the endpoint says
is where the access token gets sent, so a link out of somebody's README must not
be able to redirect the credentials by itself. See `parse_ref`.
"""

from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse

import httpx

from . import __version__, i18n
from .i18n import Failure

DEFAULT_ENDPOINT = "https://huggingface.co"
KNOWN_ENDPOINTS = (DEFAULT_ENDPOINT, "https://hf-mirror.com")
CANONICAL_HOSTS = ("huggingface.co", "hf.co")

USER_AGENT = f"hf-simple-downloader/{__version__} (+httpx)"
PAGE_LIMIT = 1000

KINDS = ("model", "dataset", "space")
_URL_PREFIX = {"model": "", "dataset": "datasets", "space": "spaces"}
_API_PREFIX = {"model": "models", "dataset": "datasets", "space": "spaces"}
_PATH_MARKERS = ("tree", "blob", "resolve", "raw", "commit")
_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def normalise_endpoint(text: str) -> str:
    """Read what was typed into the mirror field into a usable base URL.

    A bare host is assumed to be https, a trailing slash is dropped, and a path
    is kept - a hub behind a reverse proxy can live under one. An empty field
    means the default, which is what makes the field safe to clear.

    The trailing slash comes off `path` at the end rather than off the text at
    the start: stripping it first turns a half-typed "https://" into "https:",
    which then reads as a bare host and normalises to the nonsense
    "https://https:" instead of being refused.
    """
    raw = (text or "").strip().strip('"')
    if not raw:
        return DEFAULT_ENDPOINT
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise Failure(i18n.ERR_BAD_ENDPOINT.fmt(text=(text or "").strip()))
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def default_endpoint() -> str:
    """The endpoint before anything has been chosen.

    `HF_ENDPOINT` is read because it is what the rest of the ecosystem already
    uses for exactly this - somebody who has set it for `huggingface_hub` should
    not have to say it again here. A malformed value is ignored rather than
    fatal: it would otherwise stop the window opening at all.
    """
    raw = (os.environ.get("HF_ENDPOINT") or "").strip()
    if raw:
        try:
            return normalise_endpoint(raw)
        except Failure:
            pass
    return DEFAULT_ENDPOINT


def _host_of(endpoint: str) -> str:
    return (urlparse(endpoint).hostname or "").lower()


def _prefix_of(endpoint: str) -> str:
    return urlparse(endpoint).path.strip("/")


@dataclass(frozen=True)
class RepoRef:
    """A repository, a branch, optionally a folder inside it - and which Hub.

    The endpoint is carried here rather than read from a global, so a file list
    that was fetched from a mirror also downloads from that mirror even if the
    field has been changed since.
    """

    kind: str = "model"
    repo_id: str = ""
    revision: str = "main"
    subfolder: str = ""
    endpoint: str = DEFAULT_ENDPOINT

    @property
    def mirrored(self) -> bool:
        return self.endpoint.rstrip("/") != DEFAULT_ENDPOINT

    @property
    def slug(self) -> str:
        """The shortest text that `parse_ref` reads back into this reference.

        What the repository history stores. It has to be complete - a dataset
        remembered as bare `owner/name` would come back as a model and 404 - and
        it deliberately leaves the endpoint out: a mirror recorded in the history
        would be refused later by whoever changed the field, and would be a
        stale answer to "which Hub" besides. The mirror is a setting; this is a
        record of what was looked at.
        """
        prefix = _URL_PREFIX[self.kind]
        parts = ([prefix] if prefix else []) + [self.repo_id]
        if self.revision != "main" or self.subfolder:
            parts += ["tree", self.revision]
            if self.subfolder:
                parts.append(self.subfolder)
        return "/".join(parts)

    @property
    def page_url(self) -> str:
        prefix = _URL_PREFIX[self.kind]
        parts = [self.endpoint] + ([prefix] if prefix else [])
        parts += [self.repo_id, "tree", self.revision]
        if self.subfolder:
            parts.append(self.subfolder)
        return "/".join(parts)

    def __str__(self) -> str:
        tail = f":{self.revision}" if self.revision != "main" else ""
        return f"{self.repo_id}{tail}" + (f"/{self.subfolder}" if self.subfolder else "")


@dataclass(frozen=True)
class RemoteFile:
    """One downloadable file. `path` is relative to the repository root."""

    path: str
    size: int | None
    is_lfs: bool = False

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


def parse_ref(text: str, kind: str = "model", endpoint: str = DEFAULT_ENDPOINT) -> RepoRef:
    """Read anything that names a repository into a `RepoRef`.

    `kind` is the radio button in the window; a URL that says otherwise wins,
    because a link is a statement of fact and the radio button is a default.

    `endpoint` is the mirror field, and it is the only thing that decides which
    Hub is used - a pasted link never changes it. A link from huggingface.co is
    read as naming a repository and is then fetched from whatever endpoint is
    set; a link from anywhere else is refused with a message pointing at the
    field, because accepting it would mean sending the token to a host chosen by
    whoever wrote the link rather than by the person reading it.
    """
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        raise Failure(i18n.ERR_NO_REPO)

    endpoint = normalise_endpoint(endpoint)
    allowed = set(CANONICAL_HOSTS)
    if _host_of(endpoint):
        allowed.add(_host_of(endpoint))

    if "://" in raw or raw.lower().startswith(tuple(h + "/" for h in allowed)):
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
        host = (parsed.hostname or "").lower()
        if host and not any(host == h or host.endswith("." + h) for h in allowed):
            raise Failure(i18n.ERR_OTHER_HOST.fmt(host=host))
        raw = unquote(parsed.path)
        prefix = _prefix_of(endpoint)
        if prefix and host == _host_of(endpoint):
            trimmed = raw.strip("/")
            if trimmed == prefix:
                raw = ""
            elif trimmed.startswith(prefix + "/"):
                raw = trimmed[len(prefix) + 1:]

    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts or parts[0] in _PATH_MARKERS:
        raise Failure(i18n.ERR_BAD_REF.fmt(text=text.strip()))

    if parts[0].lower() in ("datasets", "dataset"):
        kind, parts = "dataset", parts[1:]
    elif parts[0].lower() in ("spaces", "space"):
        kind, parts = "space", parts[1:]
    if kind not in KINDS:
        kind = "model"

    if len(parts) >= 2 and parts[1] not in _PATH_MARKERS:
        repo_id, rest = f"{parts[0]}/{parts[1]}", parts[2:]
    else:
        repo_id, rest = parts[0], parts[1:]
    if not repo_id or repo_id in _PATH_MARKERS:
        raise Failure(i18n.ERR_BAD_REF.fmt(text=text.strip()))

    if not rest or rest[0] not in _PATH_MARKERS:
        return RepoRef(kind=kind, repo_id=repo_id, endpoint=endpoint)

    marker, rest = rest[0], rest[1:]
    revision, tail = _split_revision(rest)
    if marker in ("blob", "resolve", "raw") and tail:
        tail = tail[:-1]
    return RepoRef(
        kind=kind,
        repo_id=repo_id,
        revision=revision,
        subfolder="/".join(tail),
        endpoint=endpoint,
    )


def _split_revision(parts: list[str]) -> tuple[str, list[str]]:
    """Take the branch off the front of a path.

    A branch is one segment except when it is a ref - `refs/pr/12`,
    `refs/convert/parquet` - which is three, and those turn up on the site often
    enough (every pull request page is one) to be worth the special case.
    """
    if not parts:
        return "main", []
    if parts[0] == "refs" and len(parts) >= 3:
        return "/".join(parts[:3]), parts[3:]
    return parts[0], parts[1:]


def trust_context() -> ssl.SSLContext:
    """The certificates the OS trusts, plus the ones httpx ships with.

    httpx on its own trusts only `certifi`, and that is what breaks behind an
    antivirus that inspects HTTPS (Kaspersky, ESET, Avast): it re-signs every
    site with its own root, which it installs into the Windows store and not,
    of course, into a Python package. `create_default_context` reads the system
    store, so that root is trusted the same way a browser trusts it - and
    certifi is added on top for a machine whose store is out of date.
    """
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    return context


def make_client(timeout: float = 30.0, verify: bool = True) -> httpx.Client:
    """A client with a read timeout long enough for a stalled CDN chunk.

    `verify=False` switches certificate checking off altogether. It is the
    window's last resort for a proxy whose root is not in the system store
    either, and it is never the default.
    """
    return httpx.Client(
        timeout=httpx.Timeout(connect=15.0, read=timeout, write=timeout, pool=15.0),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        verify=trust_context() if verify else False,
    )


def headers(token: str = "") -> dict[str, str]:
    head = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        head["Authorization"] = f"Bearer {token.strip()}"
    return head


def _api(ref: RepoRef, *tail: str) -> str:
    return "/".join([ref.endpoint, "api", _API_PREFIX[ref.kind], ref.repo_id, *tail])


def _get(client: httpx.Client, url: str, ref: RepoRef, token: str) -> httpx.Response:
    """One API call, with the failures worded for the person who will read them.

    Redirects are followed here - unlike in `transfer`, where they leave the
    host and the token must not follow. The API answers on huggingface.co and
    stays there.
    """
    try:
        resp = client.get(url, headers=headers(token), follow_redirects=True)
    except httpx.HTTPError as exc:
        raise Failure(i18n.ERR_NETWORK.fmt(err=exc)) from exc
    if resp.status_code == 404:
        raise Failure(i18n.ERR_NOT_FOUND.fmt(repo=ref.repo_id))
    if resp.status_code in (401, 403):
        raise Failure(i18n.ERR_GATED.fmt(repo=ref.repo_id))
    if resp.status_code >= 400:
        raise Failure(i18n.ERR_HTTP.fmt(status=resp.status_code, url=url))
    return resp


def list_revisions(client: httpx.Client, ref: RepoRef, token: str = "") -> list[str]:
    """Branches then tags, `main` first. Never raises - this only fills a combo box."""
    try:
        data = _get(client, _api(ref, "refs"), ref, token).json()
    except (Failure, ValueError):
        return [ref.revision]
    names: list[str] = []
    for group in ("branches", "tags"):
        for item in data.get(group) or []:
            name = item.get("name")
            if name and name not in names:
                names.append(name)
    if not names:
        return [ref.revision]
    names.sort(key=lambda n: (n != "main", n.lower()))
    if ref.revision not in names:
        names.append(ref.revision)
    return names


def list_files(client: httpx.Client, ref: RepoRef, token: str = "") -> list[RemoteFile]:
    """Every file under `ref`, recursively, with its real size."""
    path = _api(ref, "tree", quote(ref.revision, safe="/"))
    if ref.subfolder:
        path += "/" + quote(ref.subfolder.strip("/"), safe="/")
    url = f"{path}?recursive=1&limit={PAGE_LIMIT}"

    files: list[RemoteFile] = []
    seen = 0
    while url:
        resp = _get(client, url, ref, token)
        try:
            page = resp.json()
        except ValueError as exc:
            raise Failure(i18n.ERR_HTTP.fmt(status=resp.status_code, url=url)) from exc
        for entry in page if isinstance(page, list) else []:
            if entry.get("type") != "file":
                continue
            lfs = entry.get("lfs") or {}
            files.append(
                RemoteFile(
                    path=entry.get("path", ""),
                    size=lfs.get("size") if lfs.get("size") is not None else entry.get("size"),
                    is_lfs=bool(lfs),
                )
            )
        seen += len(page) if isinstance(page, list) else 0
        match = _NEXT_LINK.search(resp.headers.get("link", ""))
        url = match.group(1) if match else ""

    files.sort(key=lambda f: (f.path.count("/"), f.path.lower()))
    return files


def download_url(ref: RepoRef, path: str) -> str:
    """The link `resolve` answers with a 302 to the CDN.

    `path` is repository-relative and is quoted here rather than by the caller,
    because a file name with a space or a `#` in it is ordinary on the Hub and
    would otherwise silently truncate the URL.
    """
    prefix = _URL_PREFIX[ref.kind]
    parts = [ref.endpoint] + ([prefix] if prefix else [])
    parts += [ref.repo_id, "resolve", quote(ref.revision, safe="/"), quote(path, safe="/")]
    return "/".join(parts)


def relative_path(ref: RepoRef, path: str) -> str:
    """The part of `path` below the folder the list was opened on."""
    sub = ref.subfolder.strip("/")
    if sub and path.startswith(sub + "/"):
        return path[len(sub) + 1:]
    return path
