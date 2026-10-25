# AI design

The engine is a compact but genuine alpha-beta searcher: bitboards, a transposition
table, principal-variation search, iterative deepening, an exact endgame solver and an
opening book. Everything runs in pure Python with no numeric dependencies.

- [Board representation](#board-representation)
- [Move generation](#move-generation)
- [Evaluation](#evaluation)
- [Search](#search)
- [Endgame solver](#endgame-solver)
- [Opening book](#opening-book)
- [Difficulty presets](#difficulty-presets)
- [Measured performance](#measured-performance)
- [Strength validation](#strength-validation)
- [Known limits](#known-limits)

---

## Board representation

`Position` (`core/bitboard.py`) is immutable and stores two integers:

```
black: bit i set  ⇔  square i holds a black disc
white: bit i set  ⇔  square i holds a white disc
turn : PLAYER_BLACK or PLAYER_WHITE
```

Squares are numbered row-major: `i = row * size + col`. Python integers are arbitrary
precision, so the *same* code serves 6×6 (36 bits), 8×8 (64 bits) and 10×10 (100 bits).

`Geometry` pre-computes, once per board size:

* `full` — the mask of every square;
* one `(shift, mask, direction)` triple per direction, where `mask` removes the columns
  that would wrap around after the shift;
* Zobrist keys: 64-bit random values per (square, colour) plus a side-to-move key,
  generated from a fixed seed so hashes are reproducible between runs.

Positions carry their Zobrist hash incrementally: `apply()` XORs out the captured discs,
XORs in the same squares for the mover, XORs the placed disc and the side-to-move key.
`Position._compute_zobrist()` recomputes from scratch and the tests assert the two agree
after every move of random games.

`Board` (`core/board.py`) remains the reference implementation on `list[list[int]]`. It
is what the interface uses and what the save loader validates against. A fuzz suite plays
random games at every size and asserts that both implementations agree on every legal
move and every flip set, so the fast path can never silently drift from the rules.

---

## Move generation

For each of the eight directions:

```
run  = shift(own) & opp          # first enemy disc in that direction
grow: run |= shift(run) & opp    # repeat until it stops growing
moves |= shift(run) & empty      # the square just past the run
```

The growth loop exits as soon as no new enemy disc appears, so a typical direction costs
two or three shift-and-mask operations. Flips use the same walk but keep the run only when
the square beyond it holds one of the mover's discs.

The result is exact — no false positives — and roughly **280 000 complete move
generations per second** on the reference machine (see
[Measured performance](#measured-performance)).

Legal moves are cached per position (`Position.legal_moves()`), because search, ordering
and evaluation all need the same mask.

---

## Evaluation

`evaluate(position)` returns a score from the side-to-move's perspective. It blends two
weight profiles linearly by the number of empty squares (`E` = empties):

| Term | Opening weights (`E ≥ 48`) | Endgame weights (`E ≤ 12`) | Meaning |
|---|---|---|---|
| Mobility | 190 | 45 | my legal moves − opponent's |
| Potential mobility | 45 | 10 | empty squares next to enemy discs − next to mine |
| Frontier | 38 | 12 | my discs adjacent to an empty square − theirs (fewer is better) |
| Corners | 240 | 180 | corners owned |
| X/C squares | −¾ / −⅓ of corner weight, while the corner is empty | same | squares that hand over a corner |
| Stability | 70 | 95 | corners plus edge discs anchored to them |
| Discs | 2 | 28 | disc difference (almost irrelevant early) |
| Parity | 0 | 34 | who moves last in the endgame |

Disc count barely matters in the opening — that is the classic Reversi trap — but decides
the game at the end, which is exactly what the interpolation encodes.

Terminal positions are scored `±(100 000 000 + 1 000 × disc difference)`, so a win always
beats any static advantage and a bigger win beats a smaller one.

`win_probability(position)` maps the evaluation through a logistic curve for the UI bar,
blending towards the actual disc ratio in the last ten moves so the bar does not lie when
the result is already decided.

---

## Search

`Searcher.search(position, limits)` runs iterative deepening:

1. **Depth 1 … max_depth**, each iteration re-ordering the root moves.
2. **Aspiration windows**: from depth 4 onwards the window starts at
   `previous ± 60`, widening to full if the score falls outside.
3. **Principal-variation search** inside each node: the first move gets a full window,
   siblings get a null window and are re-searched only when they improve alpha.
4. **Transposition table**: a dict keyed by the Zobrist hash storing
   `(depth, score, flag, best move)` with depth-preferred replacement and a size cap.
   Flags follow the usual exact/lower/upper convention.
5. **Move ordering**: transposition-table move first, then killer moves, then a static
   square-value table (corner ≫ edge ≫ centre; X and C squares penalised) plus a history
   heuristic updated on cutoffs.
6. **Time management**: a hard deadline checked every 2 048 nodes, plus a rule that stops
   starting a new iteration after 55 % of the budget. A completed iteration is always
   preferred over a partial one.

If an iteration is aborted, the controller keeps the best move the aborted iteration had
already established, which is what makes very tight time budgets safe.

`SearchResult` carries the move, score, depth, node count, elapsed time, principal
variation and a `complete` flag. The interface reads it for the live “depth / nodes / nps”
readout.

### Fail-safe behaviour

- Timeouts raise `SearchTimeout` internally and are caught at the root.
- `Searcher.cancel()` sets a flag checked in the inner loop; the worker joins the thread.
- If the engine ever returned an illegal move the controller falls back to the first legal
  move; the tests assert the engine never needs that fallback.

---

## Endgame solver

Two mechanisms, deliberately separated:

* **In-tree extension** — at leaf nodes with at most six empties, the search extends to
  the end of the game instead of evaluating. Cheap and always completes.
* **Root exact solve** — when the root has at most `endgame_empties` empties (12 for
  Expert, 18 for Master) and there is time left, the engine runs a full-window solve with
  exact scoring. A completed solve replaces the heuristic result; a timed-out one is
  discarded and the heuristic move stands.

`ai/endgame.py` also exposes `perfect_difference()`, an unpruned reference solver used by
the tests to prove the fast solver returns the same value on reduced endgames.

> **Why this design?** An earlier version extended to an exact solve at *every* node with
> ≤ 18 empties. That made even depth 1 unfinishable in the endgame, so the engine fell
> back to a statically ordered move and played measurably worse. Splitting cheap
> extensions from an opportunistic root solve fixed it — and the self-play result flipped
> from 1–5 to 5–1 in Master's favour.

---

## Opening book

`src/iago/ai/data/opening_book.json` holds sixteen lines of four plies, generated by
`scripts/build_book.py`:

* for each of the four standard first moves (d3, c4, f5, e6) the script ranks the
  opponent's replies at depth 4 and keeps the two best;
* each branch is extended two plies further with the same method;
* lines are named after conventional openings where they match (Tiger, Cat, Horse,
  Rabbit, Bull, Raccoon) and otherwise after their family (Diagonal, Parallel).

Every line is **replayed against the rules at load time**; an illegal line is skipped with
a warning rather than crashing the game. Book moves are used by Hard, Expert and Master.

---

## Difficulty presets

| # | Name | Time | Max depth | Exact endgame | Noise | Book |
|---|---|---|---|---|---|---|
| 1 | Easy | — | — | — | random move | no |
| 2 | Medium | — | 1 | — | ±90 | no |
| 3 | Hard | 0.6 s | 12 | 4 | ±18 | yes |
| 4 | Expert | 2.5 s | 24 | 12 | 0 | yes |
| 5 | Master | 5.0 s | 40 | 18 | 0 | yes |

Level 2's noise is applied at the root only, which produces occasional human-like
mistakes without making the engine random.

---

## Measured performance

Reference machine: Python 3.14, aarch64, `pygame-ce` 2.5.8. Reproduce with
`python scripts/bench_search.py`.

| Primitive | Rate |
|---|---|
| Move generation | **≈ 278 000 / s** |
| Position apply (place + flips + hash) | **≈ 396 000 / s** |

| Thinking budget | Median depth | Nodes | Nodes / s |
|---|---|---|---|
| 0.25 s | 5.5 | 16 384 | 63 825 |
| 0.50 s | 6.5 | 20 019 | 63 458 |
| 1.00 s | 7.5 | 43 825 | 60 585 |
| 2.50 s | 8.5 | 132 626 | 59 640 |
| 5.00 s | 8.5 | 289 792 | 57 844 |

These are mid-game positions (14–19 plies played) with the exact-endgame threshold at 12.

---

## Strength validation

`scripts/selfplay.py` plays games between two levels, alternating colours to cancel the
first-move advantage. Results (time budgets scaled to keep the runs short):

| Match | Score | Games |
|---|---|---|
| Master (5) vs Expert (4) | **5–1** (83 %) | 6 |
| Expert (4) vs Hard (3) | **4–0** | 4 |
| Hard (3) vs Medium (2) | **6–0** | 6 |
| Medium (2) vs Easy (1) | **8–0** | 8 |

Every level beats the one below it, which is the property that matters for players.

---

## Known limits

* **GIL.** Search and rendering share one interpreter. The interface stays responsive
  (the search checks for cancellation and the GIL is released every 5 ms), but a search
  thread cannot use a second core. Multiprocessing was rejected: transferring state and
  cancelling cleanly is much more complex than the gain justifies for a desktop game.
* **Depth vs. classic engines.** ~60 000 nodes/s in Python is roughly 100× slower than a
  C engine. Expert reaches 8–9 plies in 2.5 s; Edax-class engines reach far deeper. Iago
  is strong for a Python project, not a tournament entrant.
* **Endgame exactness is opportunistic.** Master solves the last 18 empties only when the
  time budget allows; otherwise it plays the best heuristic move.
* **The book is small** (16 lines, four plies). It gives opening variety and avoids the
  worst first-move blunders; it is not a competitive opening database.
