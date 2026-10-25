"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame as pg  # noqa: E402  (environment must be set first)

from .app import paths
from .app.game import Game, LaunchOptions
from .app.keymap import BINDINGS
from .branding import APP_NAME, APP_TAGLINE, VERSION
from .core.constants import DEFAULT_BOARD_SIZE, MODES, SUPPORTED_BOARD_SIZES
from .ui.layout import MAX_UI_SCALE, MIN_UI_SCALE
from .ui.theme import THEME_ORDER, THEMES
from .util.errors import IagoError
from .util.log import configure as configure_logging
from .util.log import get_logger

logger = get_logger("cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iago",
        description=f"{APP_NAME} — {APP_TAGLINE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  iago --theme midnight --level 5\n"
            "  iago --mode ava --level 4 --size 10\n"
            "  iago --fullscreen --no-sound\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument("--theme", choices=THEME_ORDER, help="colour theme")
    parser.add_argument("--mode", choices=MODES, help="game mode")
    parser.add_argument(
        "--level",
        type=int,
        choices=range(1, 6),
        help="difficulty level (1-5)",
    )
    parser.add_argument(
        "--size",
        type=int,
        choices=SUPPORTED_BOARD_SIZES,
        default=None,
        help=f"board size (default {DEFAULT_BOARD_SIZE})",
    )
    parser.add_argument("--fullscreen", action="store_true", help="start fullscreen")
    parser.add_argument("--windowed", action="store_true", help="force windowed mode")
    parser.add_argument(
        "--scale",
        type=float,
        help=f"interface scale, {MIN_UI_SCALE:g} to {MAX_UI_SCALE:g}",
    )
    parser.add_argument("--sound", dest="sound", action="store_true", default=None)
    parser.add_argument("--no-sound", dest="sound", action="store_false")
    parser.add_argument(
        "--seed", type=int, help="seed the engines for reproducible play"
    )
    parser.add_argument(
        "--data-dir", help="override the base data directory (files land in PATH/iago)"
    )
    parser.add_argument(
        "--reset-settings", action="store_true", help="ignore saved settings"
    )
    parser.add_argument(
        "--list-themes", action="store_true", help="print themes and exit"
    )
    parser.add_argument(
        "--list-controls", action="store_true", help="print controls and exit"
    )
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    parser.add_argument("--quiet", action="store_true", help="only log warnings")
    return parser


def _print_themes() -> None:
    print(f"{APP_NAME} {VERSION} — themes\n")
    for key in THEME_ORDER:
        theme = THEMES[key]
        print(f"  {key:10s} {theme.name}")
    print("\nUse --theme <key> to choose one.")


def _print_controls() -> None:
    print(f"{APP_NAME} {VERSION} — controls\n")
    current = None
    for binding in BINDINGS:
        if binding.context != current:
            current = binding.context
            print(f"{current}:")
        print(f"  {binding.display:14s} {binding.label}")
    print("\nMouse: click a marker to move, click a move in the sidebar to review.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ[paths.ENV_OVERRIDE] = os.path.abspath(args.data_dir)

    log_file = paths.log_path()
    configure_logging(verbose=args.verbose, quiet=args.quiet, log_file=log_file)
    if args.verbose:
        print(f"{APP_NAME}: logging to {log_file}", file=sys.stderr)

    if args.list_themes:
        _print_themes()
        return 0
    if args.list_controls:
        _print_controls()
        return 0

    options = LaunchOptions(
        theme=args.theme,
        mode=args.mode,
        level=args.level,
        size=args.size,
        fullscreen=args.fullscreen,
        windowed=args.windowed,
        ui_scale=args.scale,
        sound=args.sound,
        seed=args.seed,
        reset_settings=args.reset_settings,
    )

    try:
        game = Game(options)
    except pg.error as exc:  # pragma: no cover - depends on the display
        print(
            f"{APP_NAME}: could not open a window ({exc}).\n"
            "If you are on a headless machine, try SDL_VIDEODRIVER=dummy.",
            file=sys.stderr,
        )
        return 2
    except IagoError as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 2

    try:
        game.run()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        game.shutdown()
    return 0


__all__ = ["build_parser", "main"]
