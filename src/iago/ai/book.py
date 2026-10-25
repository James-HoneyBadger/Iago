"""Opening book.

The book is a JSON file of named lines.  Every line is replayed against the
reference rules at load time, so a typo can never produce an illegal move; bad
lines are skipped with a warning instead of crashing the game.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..core.board import Board
from ..core.constants import DEFAULT_BOARD_SIZE, PLAYER_BLACK, PLAYER_WHITE
from ..core.notation import move_name, parse_move
from ..util.log import get_logger

logger = get_logger("ai.book")

DEFAULT_BOOK_PATH = Path(__file__).with_name("data") / "opening_book.json"

MoveLog = Sequence[Tuple[int, int, int]]
Coords = Tuple[Tuple[int, int], ...]


@dataclass(frozen=True)
class BookLine:
    """One named opening line."""

    name: str
    moves: Coords

    @property
    def length(self) -> int:
        return len(self.moves)


class OpeningBook:
    """Lookup table from move sequence to a book continuation."""

    def __init__(self, lines: Iterable[BookLine] = (), size: int = DEFAULT_BOARD_SIZE):
        self.size = size
        self.lines: List[BookLine] = list(lines)
        self._continuations: Dict[Coords, Tuple[int, int]] = {}
        self._names: Dict[Coords, str] = {}
        self._validate()

    # ------------------------------------------------------------------

    def _validate(self) -> None:
        self._continuations.clear()
        self._names.clear()
        for line in self.lines:
            if self.size != DEFAULT_BOARD_SIZE:
                continue
            board = Board(self.size)
            legal = True
            for index, (row, col) in enumerate(line.moves):
                player = PLAYER_BLACK if index % 2 == 0 else PLAYER_WHITE
                if not board.is_valid_move(row, col, player):
                    logger.warning(
                        "Opening book line %r move %d is illegal; skipping",
                        line.name,
                        index + 1,
                    )
                    legal = False
                    break
                board.make_move(row, col, player)
            if not legal:
                continue
            for index, _ in enumerate(line.moves):
                prefix = tuple(line.moves[:index])
                if prefix not in self._continuations:
                    self._continuations[prefix] = line.moves[index]
                self._names.setdefault(prefix, line.name)

    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self._continuations

    def lookup(self, move_log: MoveLog) -> Optional[Tuple[int, int]]:
        """Return the book continuation for *move_log*, if any."""

        key = tuple((row, col) for _, row, col in move_log)
        return self._continuations.get(key)

    def name_for(self, move_log: MoveLog) -> Optional[str]:
        key = tuple((row, col) for _, row, col in move_log)
        return self._names.get(key)

    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls, path: Optional[Path] = None, size: int = DEFAULT_BOARD_SIZE
    ) -> "OpeningBook":
        """Load the book, returning an empty book when the file is unusable."""

        book_path = Path(path) if path is not None else DEFAULT_BOOK_PATH
        try:
            raw = json.loads(book_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Opening book unavailable (%s): %s", book_path, exc)
            return cls((), size)

        lines: List[BookLine] = []
        for entry in raw.get("lines", []):
            try:
                name = str(entry["name"])
                moves = tuple(parse_move(move) for move in entry["moves"])
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed book line %r: %s", entry, exc)
                continue
            lines.append(BookLine(name=name, moves=moves))
        return cls(lines, size)

    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "board_size": self.size,
            "lines": [
                {"name": line.name, "moves": [move_name(r, c) for r, c in line.moves]}
                for line in self.lines
            ],
        }


__all__ = ["BookLine", "DEFAULT_BOOK_PATH", "OpeningBook"]
