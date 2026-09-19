# Changelog

[Русская версия](CHANGELOG.ru.md)

The number in the window title, the git tag and `src/hfdl/__init__.py` always say
the same thing; the release workflow refuses to publish a tag that does not.

## 1.3.1 - 2026-09-19

### Added

- **A folder per repository.** *Make a subfolder named after the repository*, in
  **Save to**, puts the files into a folder of the repository's own name inside
  the one chosen - `Qwen/Qwen3-8B` into `...\models\Qwen3-8B` - so one **models**
  folder holds every model and the folder history keeps one line instead of one
  per download. The name is shown beside the box before anything is downloaded
  and is taken from the loaded file list, so it names the repository the files
  belong to. Whatever a name would be on Windows - a colon, a reserved device
  name - is made safe rather than refused. The folder itself is created when
  **Download** is pressed, the **On disk** column already looks inside it, and
  the folder history remembers the folder that was chosen, not the one made
  inside it. The checkbox is remembered as `repo_folder` and starts off, so
  nothing changes for anybody who does not tick it.

## 1.3.0 - 2026-09-15

### Added

- **A Windows exe in every release.** `HF_Downloader-1.3.0.exe` is the same
  program as one file, with Python and httpx inside: no install, no `uv`, no
  first-run download. `settings.json` and `downloader.log` are kept next to the
  exe. It is built by PyInstaller on a GitHub Windows runner from the tagged
  source, with the versions `uv.lock` pins, and is started once there before it
  is published. It is not code-signed, so SmartScreen may warn on the first run
  (**More info** - **Run anyway**), and an antivirus may flag it by mistake; the
  zip still does the same job, and the SHA-256 of both files is in the notes.

## 1.2.0 - 2026-09-15

### Added

- **ModelScope - public repositories only.** Pick `https://modelscope.cn` or
  `https://modelscope.ai` in the **Mirror** field and load models and datasets
  from there the same way as from the Hub: a name, a `modelscope.cn/models/...`
  page, a link into a subfolder or to one file. ModelScope's own API is used -
  real LFS sizes, `master` as the default branch, the paged dataset tree - and
  the download resumes and retries exactly as it does on huggingface.co.
  Signing in to ModelScope is **not** supported: private and approval-gated
  repositories there cannot be downloaded, the log says so each time a list is
  loaded from ModelScope, and a refusal says so instead of asking for a token.
  The HF token is never sent to ModelScope.

### Fixed

- **A redirect that arrives only on GET is followed.** A server that answers
  HEAD with 200 but redirects the GET itself would have had the redirect page
  written into the `.part` file. Downloads now walk redirects on the GET as
  well, with the token still left behind at the first host.

## 1.1.0 - 2026-09-15

### Fixed

- **HTTPS behind an antivirus that inspects it.** Kaspersky, ESET, Avast and
  corporate proxies re-sign every site with their own root, which they install
  into the system store. httpx trusted only `certifi`, so every request ended in
  `CERTIFICATE_VERIFY_FAILED`. Certificates are now checked against the system
  store as well as certifi, the same way a browser checks them, and that root is
  trusted without switching anything off.

### Added

- **A *Do not check HTTPS certificates* box** under the token field, for a proxy
  whose root is not in the system store either. It covers both the file list
  and the downloads, is remembered in `settings.json` as `verify_ssl`, and while
  it is ticked the log says so at every start. It is off by default: with it on,
  nothing protects the connection or the token from interception.

## 1.0.0 - 2026-08-16

First version.

### Added

- **A file list off any Hugging Face repository.** Models, datasets and spaces;
  anything that names one is accepted - `owner/name`, a repository page, a link
  into a subfolder, a link to a single file, a `?download=true` link out of
  somebody's README. LFS sizes are read from `lfs.size` rather than from the
  pointer, and the list follows the `Link` header past the first thousand
  entries.
- **Picking files.** Click a row or a folder to tick it, Space for a whole
  selection, and a filter box that the Select all / Clear / Invert buttons
  respect - so `.safetensors` followed by **Select all** means what it looks
  like. The ticks live in a set of paths, so they survive the filter being
  cleared.
- **An "On disk" column** that says what is already in the chosen folder before
  anything is pressed: *complete*, *partial, 43.1%*, or *other size*.
- **A history behind all three fields** - repository, mirror and save folder -
  each a drop-down of the last twelve, newest first, duplicates collapsed, and a
  right-click to drop one entry or the lot. **Browse...** is still there for a
  new folder, and picking a repository out of its history loads it. Repositories
  are stored in a canonical short form (`datasets/squad/tree/main/plain`) that
  parses back to exactly what was loaded, so one model is one entry however it
  was typed, and the field is rewritten to that form after a successful load.
- **The save folder as a drop-down** with a checkbox deciding whether the
  repository's subfolders come along.
- **Resuming.** Bytes go to `<name>.part` and are renamed into place only when
  the file is whole; Stop leaves the `.part` behind and the next Download picks
  it up from that byte, today or next week. A dropped connection is retried five
  times with a growing pause, and each retry resumes.
- **Progress, speed and time left**, per file and for the queue as a whole. The
  rate is measured over a five-second window, and bytes that were already on
  disk count towards progress but not towards speed.
- **Three files at a time** by default, one to eight; Pause and Stop take effect
  between chunks rather than at the end of a file.
- **Mirrors.** A **Mirror** field next to the branch decides which Hub is used -
  `huggingface.co` by default, `hf-mirror.com` offered in the drop-down, and
  anything else typed in and remembered, path prefixes and `host:port` included.
  `HF_ENDPOINT` from the environment is the starting value. The endpoint rides
  on the repository reference rather than in a global, so a list loaded from a
  mirror also downloads from it. A pasted link never changes the field: a
  `huggingface.co` link names a repository and is fetched from whatever mirror
  is set, and a link from any other host is refused with a message pointing at
  the field - because the field is where the token gets sent.
- **Private and gated repositories** through a token field. The token is sent to
  the endpoint's own host only - redirects to a CDN, or from a mirror back to
  `huggingface.co`, are walked by hand so the `Authorization` header is not
  carried across, and every retry re-walks from the original URL because a
  signed CDN link expires.
- **Russian and English**, switched with one button and following the Windows
  locale on the first run.
- **Refusals before the transfer starts**: free space is checked against the
  volume, and a repository path that would land outside the chosen folder is
  rejected rather than joined.
- `install.bat` builds the environment through `uv`, checks that the interpreter
  can actually import tkinter, and runs the test suite; `HF_Downloader.bat`
  opens the window and runs the install itself if there is no environment yet.
- **A Unix half of both launchers** - `install.sh` and `HF_Downloader.sh` -
  step for step the same, with the uv asset chosen by platform, `.venv/bin/`
  instead of `.venv\Scripts\`, a warning when there is no `DISPLAY`, and a
  `chmod +x` at the end so a release ZIP does not need one.
- **The banner and the language question in four shared scripts**: `logo.bat` /
  `logo.sh` print it, `lang.bat` / `lang.sh` set `LC`, and every launcher calls
  them rather than carrying its own copy. `HFDL_LANG` in the environment, then
  `lang` in `settings.json`, then the OS - the same order as `i18n.pick_lang`
  on the Python side, so a launcher's banner and the window that follows it
  cannot end up in different languages. An empty `lang` - which is what the
  file says until RU / EN has been pressed - falls through to the OS instead of
  counting as English.
