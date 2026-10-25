#!/bin/bash
# One-shot development setup: virtual environment, editable install and
# optional verification run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

echo "Setting up Iago…"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Error: $PYTHON is not installed." >&2
    exit 1
fi

VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Error: Python 3.10 or newer is required (found $VERSION)." >&2
    exit 1
fi
echo "  Python $VERSION found"

if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
    echo "  Creating .venv"
    "$PYTHON" -m venv .venv
fi

if [ -x ".venv/bin/python" ]; then
    VENV_PY=".venv/bin/python"
else
    VENV_PY=".venv/Scripts/python.exe"
fi

echo "  Installing dependencies"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -e ".[dev]"

echo "  Running the test suite"
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy "$VENV_PY" -m pytest -q

cat <<'MESSAGE'

Setup complete.

Play the game:
  ./play.sh                       # launcher (recommended)
  .venv/bin/python -m iago        # module entry point
  .venv/bin/iago                  # installed console script

Development:
  .venv/bin/pytest -q             # tests
  .venv/bin/black src tests       # format
  .venv/bin/flake8 src tests      # lint
  .venv/bin/mypy src/iago         # type-check
  .venv/bin/pylint src/iago       # static analysis
MESSAGE
