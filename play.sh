#!/bin/bash
# Iago launcher: creates the virtual environment on first use, keeps
# dependencies in sync, then starts the game. Any arguments are forwarded
# (try `./play.sh --help`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Error: $PYTHON is not installed." >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
    echo "Creating virtual environment…"
    "$PYTHON" -m venv .venv || {
        echo "Error: could not create .venv (try: sudo apt install python3-venv)" >&2
        exit 1
    }
    NEED_INSTALL=1
else
    NEED_INSTALL=0
fi

if [ -x ".venv/bin/python" ]; then
    VENV_PY=".venv/bin/python"
else
    VENV_PY=".venv/Scripts/python.exe"
fi

# Reinstall when the project metadata is newer than the last install.
STAMP=".venv/.iago_installed"
if [ "$NEED_INSTALL" = "1" ] || [ ! -f "$STAMP" ] || [ pyproject.toml -nt "$STAMP" ]; then
    echo "Installing Iago…"
    "$VENV_PY" -m pip install --quiet --upgrade pip
    "$VENV_PY" -m pip install --quiet -e . || {
        echo "Error: dependency installation failed." >&2
        exit 1
    }
    touch "$STAMP"
fi

exec "$VENV_PY" -m iago "$@"
