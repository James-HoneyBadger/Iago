#!/usr/bin/env python3
"""Generate the opening book from the engine's own analysis.

For each of the four standard first moves the script ranks the opponent's
replies at a fixed depth, keeps the two strongest, and extends each branch two
plies further.  Every line is validated against the rules when the game loads
the book, so a bad line can never reach the board.

Run from the repository root::

    python scripts/build_book.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iago.ai.book import DEFAULT_BOOK_PATH  # noqa: E402
from iago.ai.search import Searcher  # noqa: E402
from iago.core import Board, Position  # noqa: E402
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE  # noqa: E402
from iago.core.notation import OPENINGS, move_name  # noqa: E402

FIRST_MOVES = ("d3", "c4", "f5", "e6")
RANK_DEPTH = 4
BRANCH_WIDTH = 2


def rank_moves(position: Position, depth: int = RANK_DEPTH) -> list[tuple[int, int]]:
    """Return ``(square_index, score)`` pairs, best first."""

    return Searcher(position.size).rank(position, depth)


FAMILIES = {
    "d3": "Diagonal",
    "e6": "Diagonal",
    "c4": "Parallel",
    "f5": "Parallel",
}


def line_name(moves: list[tuple[int, int]], first: str) -> str:
    names = [move_name(row, col) for row, col in moves]
    for opening in OPENINGS:
        if tuple(names[: len(opening.moves)]) == opening.moves:
            return opening.name
    return f"{FAMILIES[first]} {first}"


def build_lines() -> list[dict]:
    lines: list[dict] = []
    used: dict[str, int] = {}

    for first in FIRST_MOVES:
        board = Board()
        row = int(first[1:]) - 1
        col = "abcdefgh".index(first[0])
        board.make_move(row, col, PLAYER_BLACK)

        white_replies = rank_moves(board.to_position())[:BRANCH_WIDTH]
        for reply_index, reply_score in white_replies:
            reply = divmod(reply_index, 8)
            board2 = Board.from_grid(board.grid, current_player=PLAYER_WHITE)
            board2.make_move(reply[0], reply[1], PLAYER_WHITE)

            black_replies = rank_moves(board2.to_position())[:BRANCH_WIDTH]
            for black_index, black_score in black_replies:
                black_move = divmod(black_index, 8)
                board3 = Board.from_grid(board2.grid, current_player=PLAYER_BLACK)
                board3.make_move(black_move[0], black_move[1], PLAYER_BLACK)

                white_follow = rank_moves(board3.to_position())[:1]
                if not white_follow:
                    continue
                follow_move = divmod(white_follow[0][0], 8)

                moves = [(row, col), reply, black_move, follow_move]
                base = line_name(moves, first)
                used[base] = used.get(base, 0) + 1
                suffix = "" if used[base] == 1 else f" {used[base]}"
                lines.append(
                    {
                        "name": f"{base}{suffix}",
                        "moves": [move_name(r, c) for r, c in moves],
                        "eval_white_reply": reply_score,
                        "eval_black_reply": black_score,
                    }
                )
    return lines


def main() -> int:
    lines = build_lines()
    payload = {
        "schema": 1,
        "board_size": 8,
        "generated_by": "scripts/build_book.py",
        "rank_depth": RANK_DEPTH,
        "lines": lines,
    }
    DEFAULT_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_BOOK_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} lines to {DEFAULT_BOOK_PATH}")
    for line in lines:
        print(f"  {line['name']:16s} {' '.join(line['moves'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
