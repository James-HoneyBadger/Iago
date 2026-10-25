# Changelog

All notable changes to Iago. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [4.0.0] — The Deluxe rewrite

This release replaces the internals end to end: a new engine, a new rendering
pipeline, a new state model and a new test and packaging setup. The rules and the
three game modes are unchanged, and Iago 3.0 save files still load.

### Added

**Engine**
- Bitboard position with size-generic shift-and-mask move generation (6×6, 8×8, 10×10).
- Zobrist hashing with incremental updates.
- Alpha-beta search with principal-variation search, transposition table, aspiration
  windows, iterative deepening, killer/history ordering and principal variation.
- Exact endgame solver at the root, plus cheap in-tree extensions.
- New evaluation: phase-interpolated mobility, potential mobility, frontier, corner and
  X/C-square terms, anchored-edge stability, disc difference and parity.
- Fifth difficulty level, **Master**.
- Generated opening book (16 validated lines) with conventional opening names.
- Background search worker with live depth/nodes/nps reporting and instant cancellation.
- `scripts/bench_search.py` and `scripts/selfplay.py` for reproducible validation.

**Interface**
- Seven themes including a colour-blind-safe High Contrast mode with distinct marker
  shapes.
- Supersampled anti-aliased disc sprites with specular highlights and reflected light.
- Procedural felt, linen and wood textures; bevelled board frame; cached board plate.
- 3-D flip animation (horizontal squash with colour swap), placement animation with
  overshoot easing, particle bursts, confetti, pulsing last-move ring, hover ghost and
  flip-preview tint.
- Responsive layout: resizable window, fullscreen (F11), UI scale, automatic sidebar
  collapse.
- Widget toolkit: buttons, segmented controls, toggles, sliders, tabs, scrollbars,
  tooltips and keyboard focus rings.
- Options overlay with Game / Appearance / Audio / Controls tabs.
- Controls overlay generated from the keymap, so it is always accurate.
- Statistics and achievements overlay.
- Post-game review: per-move ratings, accuracy, blunder list, key moments, clickable move
  list and replay stepping.
- Evaluation graph and opening name in the sidebar.
- Optional clocks: stopwatch and blitz with increment and timeout.
- Toast notifications for passes, saves, achievements and errors.
- F3 debug overlay (fps, layout, animation and search counters).

**Data and audio**
- Versioned, validated, atomic JSON for settings (schema 2), statistics (schema 2) and
  saves (schema 4), with migration from Iago 3.0.
- Platform data directories (XDG / AppData / Library) with `--data-dir` override.
- Autosave every ten moves and on quit, with a resume prompt at start-up.
- Eleven achievements with unlock toasts.
- Rewritten audio engine: correct 16-bit stereo buffers, ten effects, volume control and
  graceful fallback when no audio device exists.

**Project**
- Installable package (`src/iago/`) with `pyproject.toml`, console script `iago` and
  `python -m iago`.
- Command-line interface with theme, mode, level, size, scale, fullscreen, sound,
  `--seed` for reproducible engine play, data-directory and diagnostic options.
- Window title that follows the mode, difficulty and theme; animated “thinking” indicator.
- Post-game review at depth 4, with the reviewed position cached per ply.
- 414 headless tests (91 % statement coverage), including perft validation,
  bitboard/reference fuzzing, brute-force endgame cross-checks, persistence migrations,
  CLI and path-resolution coverage, scripted controller games and an executable check of
  the layering rules.
- CI on Linux, macOS and Windows across Python 3.10–3.14 with black, flake8, mypy, pylint,
  coverage and wheel-build checks.
- Documentation: user guide, technical reference, architecture, AI design, development
  guide, save format, changelog and generated screenshots.

### Changed
- `./play.sh` now upgrades its environment from `pyproject.toml` and runs the installed
  module; `./setup.sh` installs the development extra and runs the tests.
- The game requires `pygame-ce >= 2.5.4` instead of `pygame >= 2.0`.
- Undo in Human vs AI now undoes the engine's reply as well, returning you to your turn.
- Hints are recomputed instantly after every move rather than only on request.
- Settings, statistics and saves no longer live next to the source tree.
- Logging is configured centrally and written to a rotating file.

### Fixed
- The window no longer freezes while the engine thinks.
- Hand-edited save files with a missing, non-numeric or malformed field are rejected with
  a message instead of raising `KeyError`/`ValueError`; a save from a newer schema is
  refused explicitly.
- Loading a save from a different board size reconfigures the engines instead of raising
  `IndexError` on the next search.
- A search that finishes after the position changed is discarded instead of producing an
  “illegal move” error.
- Clock times recorded in a save are restored when the game is loaded.
- `Board.make_move` passes the turn to the mover's opponent, so replays and analysis no
  longer depend on the board's own turn tracking.
- Loading a finished game shows its result panel and review instead of an inert board,
  without counting the game twice.
- Sound effects played for 25 ms instead of their intended 100 ms (8-bit mono buffers were
  handed to a 16-bit stereo mixer).
- The win-probability labels no longer overlap the turn banner, and the hotkey column is
  no longer clipped.
- Boards with long capture runs were mis-generated by the propagation loop in early
  builds of the new engine; caught by perft tests.
- Theme data existed but was never applied; every visual constant now comes from a theme.
- `src/__init__.py` was not importable as a package and module imports relied on
  `sys.path` hacks.
- Bare `except Exception: pass` blocks hid save and stats failures; all I/O errors are now
  typed and logged.

### Removed
- The legacy `Reversi.py` shim, `logger.py`, `error_handling.py` and the flat `src/`
  module layout.
- `REORGANIZATION_SUMMARY.md`, `IMPLEMENTATION_SUMMARY.md` and `AI_LEVELS_VERIFICATION.md`
  (superseded by the documentation in `docs/`).
- Runtime `stats.json` and `autosave.json` from the repository; they are user data.

---

## [3.0.0] — Deluxe Edition

- Four AI levels (random, heuristic, 1 s search, 3 s search).
- Opening book, best-move hints, win-probability bar, move history.
- Wave-flip animation, options overlay, three game modes.
- Save/load/replay, programmatic sounds, statistics.
