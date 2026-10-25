"""Allow ``python -m iago`` and provide the console-script entry point."""

from __future__ import annotations

from .cli import main

__all__ = ["main"]


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
