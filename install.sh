#!/usr/bin/env bash
# ============================================================
#  The Unix half of install.bat, step for step.
#
#  Two things genuinely differ, and each is marked where it happens:
#  the uv asset is chosen by platform rather than being one .zip, and
#  the interpreter lives at .venv/bin/python rather than .venv\Scripts\.
#
#  What is deliberately the same: the step numbering, the idempotence,
#  and the two-language output through `say`.
#
#  No `set -e`, on purpose: several steps are meant to report a failure
#  and carry on - the tests failing does not undo an install that
#  happened. Every command that must succeed is checked where it runs.
# ============================================================
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

. "$SCRIPT_DIR/lang.sh"

say() { if [ "$LC" = ru ]; then echo "$2"; else echo "$1"; fi; }
die() { say "$1" "$2"; exit 1; }

SUB="HuggingFace Simple Downloader - setting up the venv"
if [ "$LC" = ru ]; then SUB="HuggingFace Simple Downloader - установка venv-окружения"; fi
bash "$SCRIPT_DIR/logo.sh" "$SUB"

case "$(uname -s)" in
    Linux | Darwin) ;;
    MINGW* | MSYS* | CYGWIN*)
        die "This is Windows - run install.bat instead." \
            "Это Windows - запускайте install.bat." ;;
    *)  die "Unsupported platform: $(uname -s)." \
            "Платформа не поддерживается: $(uname -s)." ;;
esac

UV="$SCRIPT_DIR/uv"
PY=".venv/bin/python"

# ============================================================
#  Step 1: uv
#  It is not committed, so a fresh clone has to fetch it. Unlike the
#  Windows build there is one asset per platform, so the triple has to
#  be worked out rather than hardcoded.
# ============================================================
uv_asset() {
    local os arch
    case "$(uname -s)" in
        Linux) os=unknown-linux-gnu ;;
        Darwin) os=apple-darwin ;;
    esac
    if [ "$os" = unknown-linux-gnu ] && ldd --version 2>&1 | grep -qi musl; then
        os=unknown-linux-musl
    fi
    case "$(uname -m)" in
        x86_64|amd64) arch=x86_64 ;;
        aarch64|arm64) arch=aarch64 ;;
        *)  die "Unsupported architecture: $(uname -m)." \
                "Архитектура не поддерживается: $(uname -m)." ;;
    esac
    printf 'uv-%s-%s.tar.gz' "$arch" "$os"
}

fetch() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$1" -O "$2"
    else
        die "Neither curl nor wget is installed." "Нет ни curl, ни wget."
    fi
}

if [ -x "$UV" ]; then
    say "[1/4] uv is already here" "[1/4] uv уже на месте"
else
    say "[1/4] Downloading uv..." "[1/4] Скачиваю uv..."
    ASSET=$(uv_asset) || exit 1
    mkdir -p downloads
    if ! fetch "https://github.com/astral-sh/uv/releases/latest/download/$ASSET" downloads/uv.tar.gz; then
        rm -rf downloads
        die "  ERROR: could not download uv. Check your internet access." \
            "  ОШИБКА: не удалось скачать uv. Проверьте доступ в интернет."
    fi
    mkdir -p downloads/uv_tmp
    tar -xzf downloads/uv.tar.gz -C downloads/uv_tmp
    found=$(find downloads/uv_tmp -type f -name uv | head -n 1)
    if [ -n "$found" ]; then
        mv "$found" "$UV"
        chmod +x "$UV"
    fi
    rm -rf downloads
    [ -x "$UV" ] || die \
        "  ERROR: the uv archive did not contain a uv binary." \
        "  ОШИБКА: в архиве uv не оказалось самого uv."
    say "  [OK] uv downloaded" "  [OK] uv загружен"
fi

# ============================================================
#  Step 2: the environment
#  uv sync reads pyproject.toml and uv.lock: it creates a .venv of the
#  right Python version, installs httpx and the package itself.
#
#  --managed-python is not decoration. The window needs tkinter, and a
#  distribution Python routinely ships it in a separate package that is
#  not installed (python3-tk); the interpreter uv brings along always
#  has it. If the flag is unknown (an old uv from another project),
#  fall back to a plain sync rather than failing.
# ============================================================
echo
say "[2/4] Building the .venv..." "[2/4] Собираю окружение .venv..."
if ! "$UV" sync --managed-python; then
    say "  retrying without --managed-python..." "  повтор без --managed-python..."
    if ! "$UV" sync; then
        die "  ERROR: uv sync failed. See the output above." \
            "  ОШИБКА: uv sync завершился неудачно. Смотрите вывод выше."
    fi
fi
if [ ! -x "$PY" ]; then
    die "  ERROR: uv finished, but $PY is not there." \
        "  ОШИБКА: uv отработал, но $PY не найден."
fi
say "  [OK] dependencies installed" "  [OK] зависимости установлены"

# ============================================================
#  Step 3: tkinter
#  The whole program is a window. Finding out here that the interpreter
#  cannot draw one is a message; finding out at launch is a traceback.
#
#  Importing tkinter needs no display - only opening a window does - so
#  this check is safe over ssh, and a headless box is told separately.
# ============================================================
echo
say "[3/4] Checking tkinter..." "[3/4] Проверяю tkinter..."
if ! "$PY" -c "import tkinter, hfdl" >/dev/null 2>&1; then
    say "  ERROR: this Python cannot import tkinter or hfdl." \
        "  ОШИБКА: этот Python не импортирует tkinter или hfdl."
    say "  Delete uv and .venv and run ./install.sh again." \
        "  Удалите uv и .venv и запустите ./install.sh заново."
    "$PY" -c "import tkinter, hfdl"
    exit 1
fi
say "  [OK] the window can be drawn" "  [OK] окно рисовать есть чем"
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ "$(uname -s)" = Linux ]; then
    say "  [!] No DISPLAY - the window will not open on this session." \
        "  [!] DISPLAY не задан - в этой сессии окно не откроется."
fi

# ============================================================
#  Step 4: the tests
#  All offline - no repository is contacted.
#
#  Through -m pytest rather than `uv run pytest`: the second form fails
#  right after the project is rebuilt with 'uv trampoline failed to
#  canonicalize script path'.
# ============================================================
echo
say "[4/4] Running the tests..." "[4/4] Прогоняю тесты..."
if "$PY" -m pytest -q; then
    say "  [OK] the tests passed" "  [OK] тесты прошли"
else
    say "  [!] The tests did not pass - it installed, but something is wrong." \
        "  [!] Тесты не прошли - установка состоялась, но что-то не так."
fi

# git records a mode, and a ZIP from the releases page does not. Doing it
# here costs nothing and saves the next reader a chmod they should not
# have to work out for themselves.
chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null

echo
echo "============================================================"
say "     Installation finished" "     Установка завершена"
echo
say "  ./HF_Downloader.sh  - open the window" "  ./HF_Downloader.sh  - открыть окно"
echo "============================================================"
echo
