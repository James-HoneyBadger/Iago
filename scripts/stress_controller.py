#!/usr/bin/env python3
"""Drive the controller with randomised input to shake out state bugs.

Every step performs a random interaction (board click, menu click, key press,
window resize) and then re-checks the whole game state against the board.
Use it before a release, or after touching the controller::

    python scripts/stress_controller.py --seed 1 --steps 1200
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("IAGO_DATA_DIR", str(ROOT / ".stress-data"))

import pygame as pg  # noqa: E402

from iago.app.game import Game, LaunchOptions  # noqa: E402
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE  # noqa: E402

KEYS = [
    pg.K_n,
    pg.K_r,
    pg.K_u,
    pg.K_y,
    pg.K_h,
    pg.K_SPACE,
    pg.K_d,
    pg.K_m,
    pg.K_t,
    pg.K_b,
    pg.K_v,
    pg.K_s,
    pg.K_l,
    pg.K_a,
    pg.K_o,
    pg.K_F1,
    pg.K_F3,
    pg.K_p,
    pg.K_PLUS,
    pg.K_MINUS,
    pg.K_1,
    pg.K_2,
    pg.K_5,
    pg.K_LEFT,
    pg.K_RIGHT,
    pg.K_HOME,
    pg.K_END,
    pg.K_ESCAPE,
]


def check(game: Game, step: int) -> None:
    """Assert that the controller's model still agrees with the board."""

    session = game.session
    black, white = session.score()
    counted_black = sum(row.count(PLAYER_BLACK) for row in session.board.grid)
    counted_white = sum(row.count(PLAYER_WHITE) for row in session.board.grid)
    assert (black, white) == (counted_black, counted_white), (
        f"score mismatch at step {step}: {(black, white)} vs "
        f"{(counted_black, counted_white)}"
    )
    assert session.current_player in (PLAYER_BLACK, PLAYER_WHITE)
    assert len(session.board.grid) == session.size
    assert all(len(row) == session.size for row in session.board.grid)
    assert len(session.records) == session.ply
    if session.game_over:
        assert session.winner is not None


def step_at(game: Game, rng: random.Random, steps: int) -> None:
    for index in range(steps):
        choice = rng.random()
        if choice < 0.35:
            board = game.renderer.layout.board
            game.on_click(
                (
                    rng.randint(board.x, board.right - 1),
                    rng.randint(board.y, board.bottom - 1),
                )
            )
        elif choice < 0.55:
            board = game.renderer.layout.board
            game.on_click(
                (
                    rng.randint(board.right - 60, board.right + 40),
                    rng.randint(board.y, board.bottom),
                )
            )
        elif choice < 0.90:
            game.on_key(
                rng.choice(KEYS),
                rng.choice([0, 0, 0, pg.KMOD_CTRL, pg.KMOD_SHIFT]),
                "",
            )
        else:
            game.renderer.resize(
                (rng.choice([760, 900, 1100, 1400]), rng.choice([660, 800, 1000]))
            )
        game.handle_events()
        game.update(1 / 60)
        game.draw()
        check(game, index)

        if index % 40 == 0:
            deadline = time.perf_counter() + 0.4
            while time.perf_counter() < deadline:
                game.update(1 / 60)
                game.draw()
                time.sleep(0.002)
                check(game, index)
        if game.overlay is not None and rng.random() < 0.15:
            game._close_overlay()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--level", type=int, default=1)
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    game = Game(LaunchOptions(mode="hvai", level=args.level))
    if game.overlay == "resume":
        game._discard_resume()

    try:
        step_at(game, rng, args.steps)
    except Exception:  # noqa: BLE001 - report and exit non-zero
        traceback.print_exc()
        print(f"FAILED after {args.steps} steps with seed {args.seed}")
        return 1
    finally:
        for worker in (game.worker, game.hint_worker, game.review_worker):
            worker.cancel()

    print(
        f"OK: {args.steps} randomised steps (seed {args.seed}) — "
        f"plies {game.session.ply}, mode {game.session.mode}, "
        f"size {game.session.size}, theme {game.settings.theme}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
