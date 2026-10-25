#!/usr/bin/env python3
"""Compatibility launcher for Iago.

Prefer ``./play.sh``, ``python -m iago`` or the installed ``iago`` command.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from iago.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
