#!/usr/bin/env bash
# ============================================================
#  The project's banner, in one place - the Unix half of logo.bat,
#  printing the same art.
#
#  $1, optional: a one-line subtitle, already in the language it
#  should be in. This file knows nothing about languages.
#
#  Run, not sourced: it sets nothing the caller needs, and `set -e`
#  here would then belong to somebody else's shell.
# ============================================================
set -euo pipefail

G='\033[0;32m'
Y='\033[1;33m'
NC='\033[0m'

printf '%b\n' "${G} ==================================================${NC}"
printf '%b\n' "${Y}"
cat <<'EOF'
             _                       _
 _ __  _   _| |_ _ __ __ ___   _____| | ___ _ __
| '_ \| | | | __| '__/ _` \ \ / / _ \ |/ _ \ '__|
| |_) | |_| | |_| | | (_| |\ V /  __/ |  __/ |
| .__/ \__, |\__|_|  \__,_| \_/ \___|_|\___|_|
|_|    |___/
EOF
if [ -n "${1:-}" ]; then
    echo
    echo "  $1"
fi
printf '%b\n' "${NC}${G} ==================================================${NC}"
echo
