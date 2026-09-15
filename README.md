<h1 align="center">HuggingFace Simple Downloader</h1>

<p align="center">Pick the files you actually want out of a Hugging Face repository, and put them where you want them.</p>

<p align="center">
  <img alt="Windows 10 and 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows11&logoColor=white">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Tkinter window" src="https://img.shields.io/badge/GUI-tkinter-2ea44f">
  <img alt="Package operations run through uv" src="https://img.shields.io/badge/packages-uv-261230?logo=uv&logoColor=white">
</p>

<p align="center"><b>English</b> | <a href="README.ru.md">Русский</a></p>

## Contents

- [What it is for](#what-it-is-for)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [How it is used](#how-it-is-used)
- [Resuming](#resuming)
- [Mirrors](#mirrors)
- [ModelScope](#modelscope)
- [Private and gated repositories](#private-and-gated-repositories)
- [What is remembered](#what-is-remembered)
- [Design notes](#design-notes)
- [Layout](#layout)
- [Versions and releases](#versions-and-releases)
- [If something breaks](#if-something-breaks)

## What it is for

A repository on the Hub is often 40 GB of which you want 4: one quantisation out
of six, the VAE and not the transformer, a single `.gguf`. `git clone` brings all
of it, `huggingface-cli` needs the exact file names typed out, and the browser
gives you one file at a time with no resume.

This is a window. Paste the repository, tick the files, pick the folder, press
Download.

- The **file list** is the repository's real tree, with real sizes - an LFS file
  reports the size of the model, not of its 134-byte pointer.
- The **repository and the save folder** are both drop-downs of what you used
  before, because the answer is nearly always one of them.
- **Interrupted downloads carry on** where they stopped, whether they were
  stopped by you, by the network or by a reboot last week.
- **Progress, speed and time left**, per file and for the queue as a whole.
- Several files at once (three by default), **Pause** and **Stop** that work
  immediately.
- Russian and English, switched with one button.
- **Public repositories on ModelScope** (modelscope.cn and modelscope.ai) too,
  chosen in the same Mirror field - see [ModelScope](#modelscope).

## Requirements

| | |
|---|---|
| **OS** | Windows 10 or 11 x64; Linux and macOS through the `.sh` scripts |
| **Python** | none of your own: `uv` fetches the one the window runs on |
| **Network** | for the first run, and obviously for downloading |
| **Admin rights** | not needed |

## Getting started

Take the zip from the [latest release](../../releases/latest), or clone it:

```bash
git clone https://github.com/pytraveler/huggingface-simple-downloader.git
```

Put the folder anywhere, then:

| | |
|---|---|
| **Windows** | double-click **`HF_Downloader.bat`** |
| **Linux, macOS** | `bash HF_Downloader.sh` - after the first run the scripts are executable, so `./HF_Downloader.sh` works from then on |

Both launchers run the install themselves if there is no environment yet; you
can also run `install.bat` / `bash install.sh` first to watch it happen.

> [!NOTE]
> The first run downloads `uv` (~35 MB) and a Python with tkinter (~30 MB),
> which takes about a minute. Every run after that starts instantly. Neither
> binary is committed to the repository.

The language follows the OS on the first run and is switched with the
**RU / EN** button. It is decided the same way in three places - the window,
`lang.bat` and `lang.sh` - from the same three sources, most deliberate first:

1. `HFDL_LANG` in the environment (`en` or `ru`; a full locale like `ru_RU.UTF-8`
   is understood too)
2. `lang` in `settings.json`, which is what the **RU / EN** button writes
3. the Windows UI language, or the usual `LANG` / `LC_ALL` variables on Unix

Anything unrecognised, and anything missing, means English. The point of the
order is that the banner a launcher prints and the window that opens a second
later cannot end up in different languages.

## How it is used

**1. Name the repository.** Anything that names one will do:

```text
Qwen/Qwen3-8B
https://huggingface.co/Qwen/Qwen3-8B
https://huggingface.co/black-forest-labs/FLUX.1-dev/tree/main/vae
https://huggingface.co/datasets/HuggingFaceFW/fineweb
https://huggingface.co/org/model/blob/main/unet/diffusion.safetensors
```

A link that points into a subfolder opens on that subfolder; a link to a single
file opens on the folder it is in. A link that says `datasets/` or `spaces/`
sets the kind by itself - the radio buttons are only there for what you type by
hand. Press **Load the file list**.

The field is a drop-down of the last twelve repositories that actually loaded,
newest first, and **picking one loads it** - the history is there to save the
second step as well as the first. Entries are stored in a short canonical form
that says everything needed to reopen the same view:

```text
Qwen/Qwen3-8B
datasets/squad/tree/main/plain
black-forest-labs/FLUX.1-dev/tree/main/vae
```

After a successful load the field is rewritten to that form, so what is in the
box and what is in the history are the same thing, and a long pasted URL becomes
a line you can read. Right-click any of the three history boxes - repository,
mirror, folder - to drop the entry showing or clear the list.

**2. Tick what you want.** Click a row to tick it, click a folder to tick
everything in it, or select several rows and press Space. The **Filter** box
narrows the tree, and **Select all** then applies to what is left in it - typing
`.safetensors` and pressing **Select all** means what it looks like it means.
Clearing the filter afterwards does not lose the ticks.

The **On disk** column says what is already in the chosen folder before you
press anything: *complete*, *partial, 43.1%*, or *other size*.

**3. Pick the folder.** The drop-down holds the last twelve folders you saved
into, newest first; **Browse...** is there for a new one. *Keep the
repository's subfolders* decides whether `vae/config.json` arrives as
`vae\config.json` or as `config.json` in the folder itself.

**4. Press Download.** The queue fills, three files move at a time, and the bar
above the buttons is the whole queue rather than the current file.

## Resuming

Bytes go to `<name>.part` and are moved onto the final name only when the file
is whole, so a half-downloaded model is never mistaken for a model. That `.part`
is also the record of how far you got:

* **Stop** leaves it in place. Press **Download** again - later today, or next
  week - and the transfer carries on from that byte.
* A dropped connection is retried five times with a growing pause, and each
  retry resumes rather than restarting.
* A file that is already there in full is skipped, and the queue says
  *already there* rather than downloading it again.
* **Pause** holds the connections open. If a mirror drops one while you are
  paused, that is just another retry when you resume.

## Mirrors

The **Mirror** field next to the branch says which Hub to talk to. It starts at
`https://huggingface.co`, offers `https://hf-mirror.com` (and the two ModelScope
sites, below) in the drop-down, and
remembers anything else you type - a company hub, a caching proxy, a host and
port on the local network. A bare host is assumed to be `https`, an address may
carry a path (`https://hub.example.com/hf`), and an empty field means
huggingface.co.

Everything follows the field: the file list, the sizes, the branch list, the
download links, and **Open on the site**. If `HF_ENDPOINT` is already set in the
environment - the variable `huggingface_hub` itself uses - that is the starting
value, so there is nothing to say twice.

A repository keeps the mirror it was loaded from. Changing the field after
pressing **Load the file list** does not move a queue that is already running;
it applies the next time the list is loaded.

> [!IMPORTANT]
> **A pasted link never changes the mirror.** A `huggingface.co` link is read as
> naming a repository and is then fetched from whichever mirror is set. A link
> from any other host is refused with a message pointing at the field - because
> the mirror is where the access token is sent, and a link out of somebody's
> README does not get to decide that.

One consequence worth knowing: a mirror that answers `resolve` with a redirect
back to huggingface.co is followed, but the token is **not** carried across that
hop - credentials stop at the first host, always. For public files this is
invisible. For a gated repository it means the mirror itself has to serve the
bytes; if it only redirects, load that one from huggingface.co directly.

## ModelScope

Pick `https://modelscope.cn` or `https://modelscope.ai` in the **Mirror** field.
ModelScope is not a mirror of the Hub - it has repositories of its own and an
API of its own - but it is chosen in the same place and then used the same way:

```text
Qwen/Qwen2.5-0.5B-Instruct
https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct/files
https://modelscope.ai/models/org/model/resolve/master/vae/config.json
https://modelscope.cn/datasets/modelscope/MMLU-Pro
```

Models and datasets both work, with their real sizes, a link into a subfolder
opens that subfolder, and downloads resume and retry exactly as they do from
huggingface.co. The differences worth knowing:

* The default branch is `master`, not `main`. Datasets have no branch list, so
  the branch box keeps whatever the list was opened on.
* ModelScope's *studios* (its equivalent of spaces) are not supported.
* A link from either ModelScope site is read as naming a repository once
  ModelScope is in the field. With huggingface.co in the field, a ModelScope
  link is refused with a message naming the value to pick.

> [!IMPORTANT]
> **Public repositories only.** Signing in to ModelScope is not implemented,
> so a private repository there, or one that needs the owner's approval,
> cannot be downloaded with this program. The log says so every time a list is
> loaded from ModelScope, and such a repository fails with a message saying
> exactly that. ModelScope answers *not found* for a private repository, so
> that message also covers a mistyped name. The HF token is never sent to
> ModelScope.

## Private and gated repositories

Accept the licence on huggingface.co, create a **read** token in
[Settings -> Access Tokens](https://huggingface.co/settings/tokens), and paste it
into the **HF token** field. It is remembered in `settings.json` next to the
launcher.

> [!WARNING]
> The token is sent to whatever the **Mirror** field says. That is the point of
> the field being a setting rather than something read off a link, but it does
> mean a mirror you do not trust should not be given a token.

> [!IMPORTANT]
> The token is stored as plain text. It is a read token rather than a password,
> and keeping it in the file is what makes the folder portable - but
> `settings.json` is in `.gitignore` for a reason, and if you would rather not
> have it on disk, leave the field empty and paste the token each session.

The token is sent to `huggingface.co` and to nowhere else - never to a CDN, and
never to ModelScope. A download link
answers with a redirect to a CDN, and the redirects are walked by hand
specifically so that the `Authorization` header is not carried across.

## What is remembered

`settings.json`, next to the launcher:

```text
lang               the language, once you have pressed RU / EN
recent_repos       the last twelve repositories that loaded, newest first
recent_paths       the last twelve save folders, newest first
recent_endpoints   the last twelve mirrors, newest first
endpoint           the mirror, or the ModelScope site, in use
token              the HF token, if one was entered
threads            how many files at once
keep_structure     the subfolders checkbox
verify_ssl         false once certificate checking has been switched off
last_repo          what was left in the repository field
geometry           the window's size and position
```

`last_repo` and `recent_repos` are different on purpose: the first restores the
field exactly as you left it, half-typed or wrong; the second only ever records
a repository that answered.

Deleting the file resets everything; nothing else in the program depends on it.

## Design notes

<details>
<summary>Open the design notes</summary>

**The token never goes past the first host.** A `resolve` URL answers 302 with a
pre-signed CDN link, and an `Authorization` header on that hop is a 400 from the
CDN. So redirects are walked one at a time and credentials are attached only
while the host is still the one the request started on. With a mirror set, that
first host is the mirror - which is also why the mirror is a field somebody
fills in and never something read off a pasted link.

**The endpoint rides on the `RepoRef`, not on a module-level constant.** A
mutable global would mean a queue that is halfway through a mirror starts
fetching the rest from somewhere else the moment the field is edited. Carrying
it on the reference makes "this list came from there, so its files come from
there too" true by construction.

**Every retry re-walks from the original URL.** A signed CDN link expires. If a
resume an hour later reused the resolved address, it would fetch an XML error
page and write it into the middle of a model - and the size check would only
catch that at the end, after the whole file had been transferred again.

**LFS sizes are not where you would look.** The tree endpoint reports `size` for
every entry, but for an LFS file that is the size of the pointer file, a few
hundred bytes; the real number is in `lfs.size`. Reading the wrong one would
make a 16 GB model look like a text file, and the progress bar, the ETA and the
free-space check are all built on it.

**The file list is paginated.** A thousand entries at a time, with the next page
in a `Link` header. Repositories that go past one page are not exotic - a
sharded model with per-shard indices gets there.

**Resumed bytes count towards progress but not towards speed.** A file that is
80% on disk starts at 80%, because anything else makes the bar jump backwards.
But those bytes did not come down the wire just now, so they are kept out of the
rate, which is measured over a five-second window rather than since the start -
an average since the start keeps quoting a speed from ten minutes ago, and the
ETA built on it is wrong in the direction that annoys people.

**No worker thread touches a widget.** tkinter is not thread-safe, and the
failure mode when it is touched from a thread is not an exception but a hang, on
somebody else's machine, days later. The window asks the download manager for a
snapshot on a 200 ms timer and drains a queue of already-worded messages; that
is the entire contract between the two halves.

**Free space is checked before the first byte.** Filling a volume and failing at
99% costs the whole transfer twice.

**The check marks are text, not images.** A Treeview has no checkbox of its own.
`☑` and `☐` live in the tree column's own string, which makes a click anywhere
on the row toggle the file and costs nothing; generated `PhotoImage` squares
would buy only a font question.

**The tick marks are kept in a set of paths, not in the widget.** So the filter
can rebuild the tree from scratch on every keystroke and the selection survives
it.

**A repository is remembered in a canonical form, not as it was typed.** The
same repository arrives as a bare name, as a page URL and as a link to one file
inside it, and three history entries for one model would be worse than none.
`RepoRef.slug` is the shortest text that `parse_ref` reads back into the same
reference, which is also what makes the entry complete: a dataset stored as bare
`owner/name` would come back as a model and 404. The mirror is deliberately left
out of it - it is a setting, and a mirror in the history would be a stale answer
that the field's own rules would later refuse.

**Flattening does not overwrite silently.** Two `config.json` files from
different subfolders would fight over one name with *Keep the subfolders*
switched off; those two keep their subfolders, and the log says so.

**The launchers must keep CRLF line endings, and the shell scripts must not.**
cmd.exe reads a batch file by byte offset; with bare LF it resumes in the middle
of the first long line and starts executing fragments of its own comments. In
the other direction, `#!/usr/bin/env bash\r` is a shebang naming an interpreter
whose name ends in a carriage return, and the error says "bad interpreter"
without showing why. `.gitattributes` pins both and the release workflow checks
the archive.

**The banner and the language question live in four small scripts, not in
eight.** `logo.bat` / `logo.sh` and `lang.bat` / `lang.sh` are called by every
launcher. Pasting the art into each one would be four copies of a block whose
every `|`, `\` and `` ` `` has to survive cmd's parser - and a broken copy still
prints, just wrong. `lang.*` sets `LC` in the caller, which is why the shell one
is sourced rather than run and has neither a shebang nor `set -e`.

**An empty `lang` in `settings.json` is not an answer.** The file says `""`
until the RU / EN button has been pressed, which is the ordinary case rather
than an edge one, so it has to fall through to the system's own idea of the
language instead of counting as a vote for English. Both `lang.bat` and
`i18n.pick_lang` are written around that.

</details>

## Layout

```text
HF_Downloader.bat        the launcher            HF_Downloader.sh   the same, Unix
install.bat              venv, deps, tests       install.sh         the same, Unix
lang.bat                 en or ru, decided once  lang.sh            the same, sourced
logo.bat                 the banner              logo.sh            the same art
pyproject.toml           the dependency (httpx) and the version, read from __init__.py
uv.lock                  the exact versions install.bat reproduces
settings.json            written on first run: folders, token, language
downloader.log           a log of every run
src\hfdl\
    __init__.py          the version, and nothing else
    __main__.py          python -m hfdl
    app.py               the window
    hub.py               reading a repository: what people paste, and what is in it
    transfer.py          one file, its redirects, its retries and its resume
    manager.py           the queue: N at a time, one progress figure
    config.py            settings.json
    i18n.py              every worded string, in both languages
    fmt.py               sizes, speeds and durations
tests\                   offline; no repository is contacted
.github\workflows\       a pushed tag is packed and published from here
```

## Versions and releases

The number is written down once, in `src\hfdl\__init__.py`, and everything else
reads it from there: `pyproject.toml` through hatchling, the window title, and
the first line of every session in `downloader.log` - which is what turns "it
does not work" into a bug report. [CHANGELOG.md](CHANGELOG.md) says what changed.

Releasing is a tag:

```bash
git tag v1.0.1 && git push origin v1.0.1
```

`.github/workflows/release.yml` then refuses the tag if it disagrees with
`__version__` or if either changelog has no section for it, runs the tests,
checks that every string still has both languages and that the launchers in the
archive are CRLF, and publishes a `git archive` of the tag - the same tree
anyone would get from a clone, nothing built or rewritten.

## If something breaks

1. **A download stops with an error** - press **Download** again. Retries are
   already automatic, but a repository that has gone away or a token that has
   expired needs you. The file keeps its `.part`, so nothing is lost.
2. **"is private or gated"** - accept the licence on the repository's page while
   signed in, then paste a read token into the **HF token** field. Both halves
   are needed; a token alone does not accept a licence.
3. **The window does not open** - look at `downloader.log` and at the console
   window behind it. `No module named tkinter` there means `uv` handed the venv
   an interpreter that cannot draw a window: delete `uv.exe` (or `uv`) and
   `.venv`, then run the install again. On Linux over ssh, `no display name and
   no $DISPLAY environment variable` means exactly what it says - `install.sh`
   warns about it at step 3.
4. **A file downloads over and over** - its size on disk disagrees with the
   size the Hub reports, so it is never counted as finished. The **On disk**
   column shows *other size* when that is the case; delete the file and let it
   come down again.
5. **`CERTIFICATE_VERIFY_FAILED` over and over** - something between you and
   the Hub is re-signing HTTPS: an antivirus with web scanning (Kaspersky, ESET,
   Avast) or a corporate proxy. Certificates are checked against the system
   store as well as certifi, so a root the antivirus installed into Windows is
   already trusted and this usually does not happen. If it still does, tick
   *Do not check HTTPS certificates* under the token field. The box is
   remembered, and the log says it is off at every start - with it ticked,
   nothing protects the connection or the token from interception, so switch it
   back off when you can, or exclude huggingface.co from the antivirus's HTTPS
   scanning instead.
6. **"not found on ModelScope" or "private or needs approval"** - check the
   name, the branch and the Model / Dataset switch first. If the repository
   opens in the browser only while you are signed in to ModelScope, it is not
   public, and this program cannot download it.
