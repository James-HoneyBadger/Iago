#!/usr/bin/env python3
"""Measure raw engine throughput and effective search depth.

Run from the repository root::

    python scripts/bench_search.py
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from iago.ai.search import SearchLimits, Searcher  # noqa: E402
from iago.core import Position  # noqa: E402
from iago.core.bitboard import iter_bits  # noqa: E402


def midgame_positions(count: int = 8, seed: int = 7) -> list[Position]:
    rng = random.Random(seed)
    positions = []
    for game in range(count):
        position = Position()
        for _ in range(14 + game % 6):
            moves = position.legal_move_list()
            if not moves:
                position = position.pass_turn()
                continue
            position = position.apply(*rng.choice(moves))
        positions.append(position)
    return positions


def measure(label: str, function, repeats: int = 20000) -> tuple[str, float]:
    started = time.perf_counter()
    for _ in range(repeats):
        function()
    elapsed = time.perf_counter() - started
    return label, repeats / elapsed


def main() -> int:
    positions = midgame_positions()
    sample = positions[0]

    results = [
        measure(
            "move generation /s",
            lambda: sample.geometry.move_mask(sample.own, sample.other),
        ),
        measure(
            "position apply /s",
            lambda: sample.apply_index(next(iter_bits(sample.legal_moves()))),
        ),
    ]

    print("Primitives")
    for label, value in results:
        print(f"  {label:24s} {value:>12,.0f}")

    print("\nSearch (midgame, endgame solver at 12 empties)")
    print(f"  {'budget':>7s} {'depth':>6s} {'nodes':>10s} {'nodes/s':>10s}")
    for budget in (0.25, 0.5, 1.0, 2.5, 5.0):
        depths, speeds, nodes = [], [], []
        for position in positions[:4]:
            result = Searcher(8).search(
                position,
                SearchLimits(time_limit=budget, max_depth=40, endgame_empties=12),
            )
            depths.append(result.depth)
            speeds.append(result.nps)
            nodes.append(result.nodes)
        print(
            f"  {budget:7.2f} {statistics.median(depths):6.1f} "
            f"{int(statistics.median(nodes)):10,d} {statistics.median(speeds):10,.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
