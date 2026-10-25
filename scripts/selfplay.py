#!/usr/bin/env python3
"""Self-play strength validation.

Plays a series of games between two difficulty levels, alternating colours to
cancel the first-move advantage, and reports win rates.

Examples::

    python scripts/selfplay.py --a 5 --b 4 --games 6 --time-scale 0.2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iago.ai.engine import Engine  # noqa: E402
from iago.ai.levels import LEVELS, MAX_DIFFICULTY  # noqa: E402
from iago.ai.search import SearchLimits  # noqa: E402
from iago.core import Board  # noqa: E402
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE  # noqa: E402


def play_game(level_black: int, level_white: int, time_scale: float, size: int) -> dict:
    board = Board(size)
    engines = {
        PLAYER_BLACK: Engine(level_black, size),
        PLAYER_WHITE: Engine(level_white, size),
    }
    moves = 0
    thinking = {PLAYER_BLACK: 0.0, PLAYER_WHITE: 0.0}

    while not board.game_over:
        player = board.current_player
        engine = engines[player]
        level = LEVELS[engine.level.number]
        limits = SearchLimits(
            time_limit=level.time_limit * time_scale,
            max_depth=level.max_depth,
            endgame_empties=level.endgame_empties,
            noise=level.noise,
        )
        started = time.perf_counter()
        if level.is_random:
            move = engine.get_move(board)
        else:
            result = engine.analyse_limits(board, limits)
            move = result.move
        thinking[player] += time.perf_counter() - started

        if move is None:
            if board.check_game_over():
                break
            continue

        board.make_move(move[0], move[1], player)
        engine.record_move(player, move[0], move[1])
        engines[3 - player].record_move(player, move[0], move[1])
        moves += 1
        board.check_game_over()

    return {
        "winner": board.winner,
        "black": level_black,
        "white": level_white,
        "moves": moves,
        "black_time": thinking[PLAYER_BLACK],
        "white_time": thinking[PLAYER_WHITE],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", type=int, default=MAX_DIFFICULTY, help="first level")
    parser.add_argument(
        "--b", type=int, default=MAX_DIFFICULTY - 1, help="second level"
    )
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--size", type=int, default=8)
    parser.add_argument(
        "--time-scale",
        type=float,
        default=0.2,
        help="multiplier applied to each level's thinking budget",
    )
    args = parser.parse_args()

    results = {"a_wins": 0, "b_wins": 0, "draws": 0}
    started = time.perf_counter()
    for index in range(args.games):
        a_is_black = index % 2 == 0
        black, white = (args.a, args.b) if a_is_black else (args.b, args.a)
        game = play_game(black, white, args.time_scale, args.size)
        if game["winner"] == 0:
            results["draws"] += 1
            outcome = "draw"
        else:
            winner_level = (
                game["black"] if game["winner"] == PLAYER_BLACK else game["white"]
            )
            if winner_level == args.a:
                results["a_wins"] += 1
                outcome = "A"
            else:
                results["b_wins"] += 1
                outcome = "B"
        print(
            f"game {index + 1}/{args.games}: black=L{game['black']} "
            f"white=L{game['white']} winner={outcome} moves={game['moves']} "
            f"t={game['black_time'] + game['white_time']:.1f}s"
        )

    decided = results["a_wins"] + results["b_wins"]
    score = (results["a_wins"] + 0.5 * results["draws"]) / max(1, args.games)
    print(
        f"\nL{args.a} vs L{args.b}: {results['a_wins']}-{results['b_wins']}-"
        f"{results['draws']}  score={score:.1%}"
    )
    print(f"decided games: {decided}, total time: {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
