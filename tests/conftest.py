"""Shared pytest configuration and fixtures.

SDL is pinned to the dummy drivers so the whole suite runs headless on CI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402  (must follow the SDL environment setup)

from iago.core import Board, Position  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _pygame_display():
    """Ensure pygame has a (headless) display for surface conversions."""

    import pygame

    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    pygame.quit()


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """An isolated application data directory for the duration of a test."""

    from iago.app import paths

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv(paths.ENV_OVERRIDE, str(base))
    return paths.data_dir()


@pytest.fixture()
def board() -> Board:
    return Board()


@pytest.fixture()
def position() -> Position:
    return Position()


@pytest.fixture()
def played_board() -> Board:
    """A board a few moves into a standard Tiger line."""

    board = Board()
    board.make_move(2, 3, 1)  # d3
    board.make_move(2, 4, 2)  # e3
    board.make_move(2, 2, 1)  # c3
    return board
