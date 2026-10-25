# Contributing to Iago

Thanks for taking the time to help. This guide covers the workflow, the quality bar and
the conventions the codebase uses.

## Getting set up

```bash
git clone https://github.com/James-HoneyBadger/Iago_Deluxe.git
cd Iago_Deluxe
./setup.sh                       # venv + editable install + tests
.venv/bin/pip install pre-commit && .venv/bin/pre-commit install
```

Python 3.10 or newer is required. The runtime dependency is `pygame-ce`; everything else
is in the `dev` extra.

## Before you open a pull request

Run the same checks CI runs:

```bash
.venv/bin/black src tests scripts main.py     # format
.venv/bin/flake8 src tests scripts main.py    # lint
.venv/bin/mypy src/iago                       # types
.venv/bin/pylint src/iago                     # static analysis
.venv/bin/pytest -q                           # tests (headless, ~15 s)
```

All five should be clean. If a change alters behaviour, add or update a test — the suite
is the contract, not an afterthought.

## What a good change looks like

- **One idea per pull request.** A fix plus unrelated refactors are hard to review.
- **Surgical edits.** Keep the diff focused; avoid reformatting untouched files.
- **Tests with the change.** Bug fixes get a regression test that fails without the fix.
- **Docs when behaviour is visible.** The user guide, README control table or AI design
  document should match what the code does.
- **No dead code, no bare `except:`** and no debug prints. Use `iago.util.log.get_logger`.
- **No new binary assets.** Textures, discs, icons and sounds are generated at runtime.
  The only committed images are documentation screenshots.

## Where things live

| If you are changing… | Look at |
|---|---|
| rules, move legality | `src/iago/core/board.py` (reference) and `core/bitboard.py` (fast) |
| evaluation or search | `src/iago/ai/` |
| difficulty behaviour | `src/iago/ai/levels.py` |
| colours, spacing, fonts | `src/iago/ui/theme.py`, `ui/layout.py` |
| a screen or widget | `src/iago/ui/` |
| commands, shortcuts, state flow | `src/iago/app/game.py`, `app/keymap.py` |
| persistence or migrations | `src/iago/app/persistence.py` |
| tests | `tests/` |

[ARCHITECTURE.md](docs/ARCHITECTURE.md) explains the layering; keep new imports pointing
downwards.

## The rules are sacred

Reversi has no house rules here. If you touch move generation, flip detection or the
pass rule, change **both** implementations (`Board` and `Position`) and run the fuzz
tests. Then check the published perft counts still pass:

```bash
.venv/bin/pytest tests/test_bitboard.py -q
```

## Engine changes

Anything that changes move choice should come with:

1. a unit test in `tests/test_search.py`;
2. `python scripts/bench_search.py` output before/after (depth and nodes/s);
3. if it targets strength, a short self-play match:

   ```bash
   python scripts/selfplay.py --a 5 --b 4 --games 6 --time-scale 0.15
   ```

Report the numbers in the pull request. "Feels stronger" is not evidence; a score table
is.

Note that time-budgeted searches are non-deterministic by nature. Tests should assert on
invariants (legal move, depth reached, node counts) rather than exact scores unless the
search is fixed-depth.

## Style

- **Formatting** is `black` (88 columns). Do not hand-format.
- **Imports**: absolute inside the package (`from ..core.board import Board`), grouped by
  stdlib / third-party / local.
- **Typing**: public functions are annotated; `mypy` runs with `check_untyped_defs`.
  Prefer precise types over `Any`.
- **Docstrings**: explain *why* and any non-obvious invariant. Do not restate the
  signature. Module docstrings state the module's responsibility.
- **Comments** are for the surprising parts only. If a line needs a comment to be
  readable, consider renaming first.
- **Naming**: British spelling in prose, American in identifiers where it is conventional
  (`color` in pygame APIs).
- **Performance-sensitive code** (`Geometry.move_mask`, `Geometry.flips`,
  `Searcher._negamax`, `evaluate`) may be dense; keep it readable and profile before
  optimising.

## User-visible text

Interface strings are user-facing and should be short, warm and specific. Prefer
"Saved to saved_game.json" over "OK". Error toasts should say what went wrong and, where
possible, what to do next.

## Commits and pull requests

- Write commit messages in the imperative mood: *"Add exact endgame solver"*, not
  *"Added"*.
- Reference issues when relevant (`Fixes #42`).
- Describe the change, the reasoning, and how you verified it.
- Screenshots are welcome for visual changes; `python scripts/generate_screenshots.py`
  regenerates the documentation set.
- The maintainers may ask for a change to keep the architecture or the UX consistent —
  that is a discussion, not a rejection.

## Reporting bugs

Include:

- the version (`iago --version`) and platform,
- what you did, what you expected, what happened,
- the log from the data directory (`iago --verbose` prints its location),
- for rendering issues, a screenshot and the theme and window size.

For engine issues, the position (moves in algebraic notation) and the difficulty level
make the report reproducible — most engine behaviour depends on both.

## Code of conduct

Be decent. Assume good faith, criticise code rather than people, and keep discussion
focused on making the game better.

## License

By contributing you agree that your work is licensed under the project's MIT license.
