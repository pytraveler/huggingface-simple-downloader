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

**ModelScope is chosen in the same field, but it is not a mirror.** modelscope.cn
and modelscope.ai speak an API of their own - `/api/v1/...`, answers wrapped in
`{"Code", "Data"}`, `master` rather than `main`, no spaces - so every function
that talks to a hub asks `RepoRef.modelscope` first. Only public repositories are
supported there: ModelScope's own sign-in is not implemented, and the HF token is
never sent to it (`token_for`).
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
MODELSCOPE_HOSTS = ("modelscope.cn", "modelscope.ai")
KNOWN_ENDPOINTS = (
    DEFAULT_ENDPOINT,
    "https://hf-mirror.com",
    "https://modelscope.cn",
    "https://modelscope.ai",
)
CANONICAL_HOSTS = ("huggingface.co", "hf.co")
HF_REVISION = "main"
MS_REVISION = "master"

USER_AGENT = f"hf-simple-downloader/{__version__} (+httpx)"
PAGE_LIMIT = 1000
MS_PAGE_SIZE = 500
MS_MAX_PAGES = 1000

KINDS = ("model", "dataset", "space")
_URL_PREFIX = {"model": "", "dataset": "datasets", "space": "spaces"}
_API_PREFIX = {"model": "models", "dataset": "datasets", "space": "spaces"}
_MS_PREFIX = {"model": "models", "dataset": "datasets"}
_PATH_MARKERS = ("tree", "blob", "resolve", "raw", "commit")
_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"')

_UNSAFE_IN_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


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


def _modelscope_domain(host: str) -> str:
    """`modelscope.cn` for `www.modelscope.cn` or its CDN, '' for anything else."""
    host = host.lower()
    for domain in MODELSCOPE_HOSTS:
        if host == domain or host.endswith("." + domain):
            return domain
    return ""


def is_modelscope(url: str) -> bool:
    """Whether an endpoint - or any URL, a CDN link included - belongs to ModelScope."""
    return bool(_modelscope_domain(_host_of(url)))


def default_revision(endpoint: str) -> str:
    return MS_REVISION if is_modelscope(endpoint) else HF_REVISION


def token_for(ref: "RepoRef", token: str) -> str:
    """The token to send for this repository: none at all to ModelScope.

    An HF token means nothing to ModelScope, and handing it to a host that did
    not issue it is exactly what the rest of this program is built to avoid.
    """
    return "" if ref.modelscope else token


@dataclass(frozen=True)
class RepoRef:
    """A repository, a branch, optionally a folder inside it - and which Hub.

    The endpoint is carried here rather than read from a global, so a file list
    that was fetched from a mirror also downloads from that mirror even if the
    field has been changed since.
    """

    kind: str = "model"
    repo_id: str = ""
    revision: str = HF_REVISION
    subfolder: str = ""
    endpoint: str = DEFAULT_ENDPOINT

    @property
    def mirrored(self) -> bool:
        return self.endpoint.rstrip("/") != DEFAULT_ENDPOINT

    @property
    def modelscope(self) -> bool:
        return is_modelscope(self.endpoint)

    @property
    def default_revision(self) -> str:
        return default_revision(self.endpoint)

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
        if self.revision != self.default_revision or self.subfolder:
            parts += ["tree", self.revision]
            if self.subfolder:
                parts.append(self.subfolder)
        return "/".join(parts)

    @property
    def folder_name(self) -> str:
        """A folder name for this repository, safe to create on any platform.

        The name without the owner - `Qwen3-8B` out of `Qwen/Qwen3-8B` - because
        that is what the model is called everywhere else, and a tree of owner
        folders is not what somebody browsing their models is looking for. What
        Windows will not accept in a name is replaced rather than refused: a
        repository is not going to fail to download over its own punctuation.
        Anything that would name a folder outside the chosen one comes back
        empty, and the caller then saves into the chosen folder itself.
        """
        name = self.repo_id.rsplit("/", 1)[-1].strip()
        cleaned = _UNSAFE_IN_NAME.sub("-", name).strip().rstrip(". ")
        if cleaned.split(".", 1)[0].upper() in _RESERVED_NAMES:
            cleaned = "_" + cleaned
        return cleaned

    @property
    def page_url(self) -> str:
        if self.modelscope:
            return "/".join([self.endpoint, _MS_PREFIX[self.kind], self.repo_id, "files"])
        prefix = _URL_PREFIX[self.kind]
        parts = [self.endpoint] + ([prefix] if prefix else [])
        parts += [self.repo_id, "tree", self.revision]
        if self.subfolder:
            parts.append(self.subfolder)
        return "/".join(parts)

    def __str__(self) -> str:
        tail = f":{self.revision}" if self.revision != self.default_revision else ""
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

    With ModelScope in the field, links from either ModelScope site are read the
    same way - `/models/owner/name/files`, `/file/view/master/...` included - and
    a ModelScope link with anything else in the field is refused with a message
    that names the value to pick.
    """
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        raise Failure(i18n.ERR_NO_REPO)

    endpoint = normalise_endpoint(endpoint)
    modelscope = is_modelscope(endpoint)
    allowed = set(CANONICAL_HOSTS)
    if _host_of(endpoint):
        allowed.add(_host_of(endpoint))
    if modelscope:
        allowed.update(MODELSCOPE_HOSTS)

    bare_hosts = allowed | set(MODELSCOPE_HOSTS) | {"www." + h for h in MODELSCOPE_HOSTS}
    if "://" in raw or raw.lower().startswith(tuple(h + "/" for h in bare_hosts)):
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
        host = (parsed.hostname or "").lower()
        if host and not any(host == h or host.endswith("." + h) for h in allowed):
            if _modelscope_domain(host):
                raise Failure(i18n.ERR_MS_LINK.fmt(host=host))
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

    head = parts[0].lower()
    if head in ("datasets", "dataset"):
        kind, parts = "dataset", parts[1:]
    elif head in ("spaces", "space") or (modelscope and head in ("studios", "studio")):
        kind, parts = "space", parts[1:]
    elif modelscope and head in ("models", "model"):
        kind, parts = "model", parts[1:]
    if kind not in KINDS:
        kind = "model"
    if modelscope and kind == "space":
        raise Failure(i18n.ERR_MS_NO_SPACE)
    if not parts:
        raise Failure(i18n.ERR_BAD_REF.fmt(text=text.strip()))

    if len(parts) >= 2 and parts[1] not in _PATH_MARKERS:
        repo_id, rest = f"{parts[0]}/{parts[1]}", parts[2:]
    else:
        repo_id, rest = parts[0], parts[1:]
    if not repo_id or repo_id in _PATH_MARKERS:
        raise Failure(i18n.ERR_BAD_REF.fmt(text=text.strip()))

    if modelscope and rest[:2] == ["file", "view"]:
        rest = ["blob"] + rest[2:]
    base = default_revision(endpoint)
    if not rest or rest[0] not in _PATH_MARKERS:
        return RepoRef(kind=kind, repo_id=repo_id, revision=base, endpoint=endpoint)

    marker, rest = rest[0], rest[1:]
    revision, tail = _split_revision(rest, base)
    if marker in ("blob", "resolve", "raw") and tail:
        tail = tail[:-1]
    return RepoRef(
        kind=kind,
        repo_id=repo_id,
        revision=revision,
        subfolder="/".join(tail),
        endpoint=endpoint,
    )


def _split_revision(parts: list[str], default: str = HF_REVISION) -> tuple[str, list[str]]:
    """Take the branch off the front of a path.

    A branch is one segment except when it is a ref - `refs/pr/12`,
    `refs/convert/parquet` - which is three, and those turn up on the site often
    enough (every pull request page is one) to be worth the special case.
    """
    if not parts:
        return default, []
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


def _ms_api(ref: RepoRef, *tail: str) -> str:
    return "/".join([ref.endpoint, "api", "v1", _MS_PREFIX[ref.kind], ref.repo_id, *tail])


def _get(client: httpx.Client, url: str, ref: RepoRef, token: str) -> httpx.Response:
    """One API call, with the failures worded for the person who will read them.

    Redirects are followed here - unlike in `transfer`, where they leave the
    host and the token must not follow. The API answers on huggingface.co and
    stays there.
    """
    try:
        resp = client.get(url, headers=headers(token_for(ref, token)), follow_redirects=True)
    except httpx.HTTPError as exc:
        raise Failure(i18n.ERR_NETWORK.fmt(err=exc)) from exc
    if resp.status_code == 404:
        if ref.modelscope:
            raise Failure(i18n.ERR_MS_NOT_FOUND.fmt(repo=ref))
        raise Failure(i18n.ERR_NOT_FOUND.fmt(repo=ref.repo_id))
    if resp.status_code in (401, 403):
        if ref.modelscope:
            raise Failure(i18n.ERR_MS_PRIVATE.fmt(repo=ref.repo_id))
        raise Failure(i18n.ERR_GATED.fmt(repo=ref.repo_id))
    if resp.status_code >= 400:
        raise Failure(i18n.ERR_HTTP.fmt(status=resp.status_code, url=url))
    return resp


def list_revisions(client: httpx.Client, ref: RepoRef, token: str = "") -> list[str]:
    """Branches then tags, the default branch first. Never raises - this only fills a combo box."""
    try:
        if ref.modelscope:
            names = _ms_revisions(client, ref)
        else:
            data = _get(client, _api(ref, "refs"), ref, token).json()
            names = [
                item.get("name")
                for group in ("branches", "tags")
                for item in data.get(group) or []
            ]
    except (Failure, ValueError, AttributeError, TypeError):
        return [ref.revision]
    unique: list[str] = []
    for name in names:
        if name and isinstance(name, str) and name not in unique:
            unique.append(name)
    if not unique:
        return [ref.revision]
    unique.sort(key=lambda n: (n != ref.default_revision, n.lower()))
    if ref.revision not in unique:
        unique.append(ref.revision)
    return unique


def _ms_revisions(client: httpx.Client, ref: RepoRef) -> list[str]:
    """ModelScope lists branches for models only; a dataset keeps what it was opened on."""
    if ref.kind != "model":
        return []
    data = _ms_data(_get(client, _ms_api(ref, "revisions"), ref, ""), ref)
    found = data.get("RevisionMap") or {}
    return [
        item.get("Revision")
        for group in ("Branches", "Tags")
        for item in found.get(group) or []
    ]


def list_files(client: httpx.Client, ref: RepoRef, token: str = "") -> list[RemoteFile]:
    """Every file under `ref`, recursively, with its real size."""
    if ref.modelscope:
        files = _ms_files(client, ref)
    else:
        files = _hf_files(client, ref, token)
    files.sort(key=lambda f: (f.path.count("/"), f.path.lower()))
    return files


def _hf_files(client: httpx.Client, ref: RepoRef, token: str) -> list[RemoteFile]:
    path = _api(ref, "tree", quote(ref.revision, safe="/"))
    if ref.subfolder:
        path += "/" + quote(ref.subfolder.strip("/"), safe="/")
    url = f"{path}?recursive=1&limit={PAGE_LIMIT}"

    files: list[RemoteFile] = []
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
        match = _NEXT_LINK.search(resp.headers.get("link", ""))
        url = match.group(1) if match else ""
    return files


def _ms_data(resp: httpx.Response, ref: RepoRef) -> dict:
    """The `Data` out of ModelScope's `{"Code", "Data", "Message"}` envelope."""
    try:
        body = resp.json()
    except ValueError as exc:
        raise Failure(i18n.ERR_HTTP.fmt(status=resp.status_code, url=resp.request.url)) from exc
    data = body.get("Data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


def _ms_files(client: httpx.Client, ref: RepoRef) -> list[RemoteFile]:
    """A ModelScope file list: one answer for a model, pages for a dataset.

    The model endpoint returns the whole tree at once, whatever page size is
    asked for. The dataset one pages, and says how many entries there are in
    `TotalCount` - folders included, so that is what the count is checked
    against. A branch that does not exist is not a 404 there but a success with
    `Files: null`, which is why `None` and an empty list mean different things.

    `Size` is the real size of an LFS file, not of its pointer, and a subfolder
    is filtered here rather than asked for, because the two endpoints do not
    agree on how to ask.
    """
    rev = quote(ref.revision, safe="")
    entries: list[dict] = []
    if ref.kind == "model":
        url = _ms_api(ref, "repo", "files") + f"?Revision={rev}&Recursive=true"
        batch = _ms_data(_get(client, url, ref, ""), ref).get("Files")
        if batch is None:
            raise Failure(i18n.ERR_MS_NOT_FOUND.fmt(repo=ref))
        entries = list(batch)
    else:
        for page in range(1, MS_MAX_PAGES + 1):
            url = _ms_api(ref, "repo", "tree") + (
                f"?Revision={rev}&Root=/&Recursive=True&PageNumber={page}&PageSize={MS_PAGE_SIZE}"
            )
            data = _ms_data(_get(client, url, ref, ""), ref)
            batch = data.get("Files")
            if batch is None and page == 1:
                raise Failure(i18n.ERR_MS_NOT_FOUND.fmt(repo=ref))
            batch = batch or []
            entries.extend(batch)
            total = data.get("TotalCount")
            if not batch:
                break
            if isinstance(total, int):
                if len(entries) >= total:
                    break
            elif len(batch) < MS_PAGE_SIZE:
                break

    sub = ref.subfolder.strip("/")
    files: list[RemoteFile] = []
    for entry in entries:
        path = entry.get("Path") or ""
        if entry.get("Type") != "blob" or not path:
            continue
        if sub and not path.startswith(sub + "/"):
            continue
        size = entry.get("Size")
        files.append(
            RemoteFile(
                path=path,
                size=size if isinstance(size, int) else None,
                is_lfs=bool(entry.get("IsLFS")),
            )
        )
    return files


def download_url(ref: RepoRef, path: str) -> str:
    """The link `resolve` answers with a 302 to the CDN.

    `path` is repository-relative and is quoted here rather than by the caller,
    because a file name with a space or a `#` in it is ordinary on the Hub and
    would otherwise silently truncate the URL.

    ModelScope has `resolve` for models only; a dataset file is fetched through
    the API, which redirects an LFS file to the same kind of CDN.
    """
    if ref.modelscope:
        if ref.kind == "dataset":
            return _ms_api(ref, "repo") + (
                f"?Revision={quote(ref.revision, safe='')}&FilePath={quote(path, safe='')}"
            )
        return "/".join([
            ref.endpoint, "models", ref.repo_id, "resolve",
            quote(ref.revision, safe="/"), quote(path, safe="/"),
        ])
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
