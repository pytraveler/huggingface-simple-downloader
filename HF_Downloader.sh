#!/usr/bin/env bash
# ============================================================
#  Open the window. First run installs; every run after that is instant.
#  The Unix half of HF_Downloader.bat.
#
#  The terminal stays in front of the window on purpose: it and
#  downloader.log are the two places an error goes, and a GUI that
#  vanishes without either is a bug report nobody can answer.
# ============================================================
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

. "$SCRIPT_DIR/lang.sh"

say() { if [ "$LC" = ru ]; then echo "$2"; else echo "$1"; fi; }

SUB="HuggingFace Simple Downloader - opening the window"
if [ "$LC" = ru ]; then SUB="HuggingFace Simple Downloader - открываю окно"; fi
bash "$SCRIPT_DIR/logo.sh" "$SUB"

PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
    say "  The environment is not built yet - running install.sh first." \
        "  Окружение ещё не собрано - сначала запускаю install.sh."
    echo
    bash "$SCRIPT_DIR/install.sh" || exit 1
    [ -x "$PY" ] || exit 1
fi

if ! "$PY" -m hfdl; then
    echo
    say "  The window closed with an error. See downloader.log next to this file." \
        "  Окно закрылось с ошибкой. Смотрите downloader.log рядом с этим файлом."
    exit 1
fi
