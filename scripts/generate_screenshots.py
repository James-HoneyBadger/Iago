#!/usr/bin/env python3
"""Render documentation screenshots headlessly.

Usage::

    python scripts/generate_screenshots.py [--out docs/images]

Every image is produced by the real renderer against the real application
state, so the documentation can never drift away from the product.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from iago.ai import Engine  # noqa: E402
from iago.app.analysis import analyse_moves  # noqa: E402
from iago.app.session import Session  # noqa: E402
from iago.app.settings import GameSettings, GameStats, LevelRecord  # noqa: E402
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE  # noqa: E402
from iago.ui.overlays import GameOverData, OptionsData  # noqa: E402
from iago.ui.renderer import RenderModel, Renderer  # noqa: E402
from iago.ui.theme import get_theme  # noqa: E402

WINDOW = (1100, 800)
LINE = (
    (PLAYER_BLACK, 2, 3),
    (PLAYER_WHITE, 2, 4),
    (PLAYER_BLACK, 3, 2),
    (PLAYER_WHITE, 1, 3),
    (PLAYER_BLACK, 4, 5),
    (PLAYER_WHITE, 5, 5),
    (PLAYER_BLACK, 5, 4),
    (PLAYER_WHITE, 3, 5),
    (PLAYER_BLACK, 2, 2),
    (PLAYER_WHITE, 1, 2),
    (PLAYER_BLACK, 0, 1),
    (PLAYER_WHITE, 5, 3),
    (PLAYER_BLACK, 4, 6),
    (PLAYER_WHITE, 3, 6),
)


def build_session() -> Session:
    session = Session(size=8, mode="hvai", player_color=PLAYER_BLACK, level=4)
    for player, row, col in LINE:
        if session.is_legal(row, col):
            session.apply_move(row, col)
    return session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs" / "images"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((10, 10))

    session = build_session()
    hint = Engine(4, session.size).quick_hint(session.board)

    print("Rendering screenshots…")
    for theme_key in ("classic", "midnight", "wood", "contrast"):
        theme = get_theme(theme_key)
        renderer = Renderer(WINDOW, 8, theme, 1.0)
        model = RenderModel(
            session=session,
            theme=theme,
            hint_move=hint,
            hint_text="Hint: c4" if hint else "",
            hover_cell=(3, 3),
            sidebar_footer="Click a move to review it",
        )
        renderer.sync_scores(*session.score())
        renderer.draw(model)
        pygame.image.save(renderer.surface, out / f"board-{theme_key}.png")
        print(f"  wrote docs/images/board-{theme_key}.png")

    theme = get_theme("classic")
    renderer = Renderer(WINDOW, 8, theme, 1.0)
    renderer.sync_scores(*session.score())

    # Options overlay — appearance tab
    options_theme = get_theme("midnight")
    renderer.set_theme(options_theme)
    model = RenderModel(
        session=session,
        theme=options_theme,
        overlay="options",
        overlay_data=OptionsData(GameSettings(), tab="Game"),
        hint_move=hint,
    )
    renderer.draw(model)
    pygame.image.save(renderer.surface, out / "options.png")
    print("  wrote docs/images/options.png")

    model = RenderModel(
        session=session,
        theme=options_theme,
        overlay="options",
        overlay_data=OptionsData(GameSettings(), tab="Appearance"),
    )
    renderer.draw(model)
    pygame.image.save(renderer.surface, out / "themes.png")
    print("  wrote docs/images/themes.png")

    model = RenderModel(session=session, theme=options_theme, overlay="help")
    renderer.draw(model)
    pygame.image.save(renderer.surface, out / "controls.png")
    print("  wrote docs/images/controls.png")

    # Statistics with plausible data
    stats = GameStats(
        games_played=42,
        games_won=24,
        games_lost=14,
        games_drawn=4,
        total_moves=42 * 57,
        best_score=52,
        win_streak=6,
        loss_streak=3,
        current_streak=2,
        fastest_win_moves=38,
        by_level={
            1: LevelRecord(played=4, won=4, best_score=64),
            2: LevelRecord(played=8, won=6, lost=2, best_score=56),
            3: LevelRecord(played=12, won=8, lost=3, drawn=1, best_score=48),
            4: LevelRecord(played=11, won=5, lost=5, drawn=1, best_score=44),
            5: LevelRecord(played=7, won=1, lost=4, drawn=2, best_score=38),
        },
        achievements=["first_win", "ten_wins", "beat_master", "shutout", "streak_five"],
    )
    model = RenderModel(
        session=session, theme=options_theme, overlay="stats", stats=stats
    )
    renderer.draw(model)
    pygame.image.save(renderer.surface, out / "statistics.png")
    print("  wrote docs/images/statistics.png")

    # A finished game with a review
    finished = build_session()
    while not finished.game_over:
        moves = finished.legal_moves()
        if not moves:
            finished.play_pending_pass()
            continue
        finished.apply_move(*moves[0])
    review = analyse_moves(finished.to_move_log(), finished.size, depth=2)
    model = RenderModel(
        session=finished,
        theme=options_theme,
        overlay="gameover",
        overlay_data=GameOverData(
            session=finished,
            review=review,
            review_progress=(len(finished.records), len(finished.records)),
        ),
        review=review,
    )
    renderer.draw(model)
    pygame.image.save(renderer.surface, out / "game-over.png")
    print("  wrote docs/images/game-over.png")

    # Compact window without the sidebar, 10x10 board
    compact = Session(size=10, mode="hvh", player_color=PLAYER_BLACK, level=3)
    first_move = compact.legal_moves()[0]
    compact.apply_move(*first_move)
    small = Renderer((780, 700), 10, get_theme("ocean"), 1.0)
    small.sync_scores(*compact.score())
    model = RenderModel(
        session=compact,
        theme=get_theme("ocean"),
        hint_move=compact.legal_moves()[0] if compact.legal_moves() else None,
    )
    small.draw(model)
    pygame.image.save(small.surface, out / "compact-10x10.png")
    print("  wrote docs/images/compact-10x10.png")

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
