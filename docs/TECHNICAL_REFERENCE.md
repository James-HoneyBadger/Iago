# Iago — Technical Reference

The module-by-module reference for working on Iago: public API, invariants, and the rules
that keep the layers apart. For the *why* behind the design read
[ARCHITECTURE.md](ARCHITECTURE.md); for the engine read [AI_DESIGN.md](AI_DESIGN.md).

- [Conventions](#conventions)
- [Dependency rules](#dependency-rules)
- [core](#core)
- [ai](#ai)
- [ui](#ui)
- [app](#app)
- [util](#util)
- [Invariants to preserve](#invariants-to-preserve)
- [Extension recipes](#extension-recipes)
- [Error taxonomy](#error-taxonomy)
- [Testing map](#testing-map)

---

## Conventions

| Convention | Rule |
|---|---|
| Player ids | `PLAYER_BLACK = 1`, `PLAYER_WHITE = 2`; `opponent(player)` flips them. Never hard-code the constant for "the other side". |
| Board size | 6, 8 or 10 in the game (`SUPPORTED_BOARD_SIZES`); `Position` accepts 4–12 for tests. |
| Coordinates | `(row, col)`, zero-based, row 0 at the top. |
| Bit indexing | `bit = 1 << (row * size + col)` — row-major. |
| Scores | Engine scores are **from the side to move**; UI win probabilities are **from Black**. |
| Time | Monotonic seconds (`time.monotonic`) in the model, `pygame.time.get_ticks()/1000` for animations. |
| Randomness | Every engine and searcher takes an optional `seed`; nothing calls `random` globally. |
| pygame | Only `ui/*` and `app/audio.py`, `app/game.py`, `cli.py` touch pygame. `core`, `ai`, `app/session.py`, `app/settings.py`, `app/persistence.py`, `app/analysis.py` are pure Python. |

---

## Dependency rules

```
app  ──►  ui  ──►  ai  ──►  core
 └───────┴──────┴──────┴──►  util
```

- `core` imports nothing from the project except `util`.
- `ai` imports `core` (and `util.log`).
- `ui` imports `core`, `ai` (for `SearchResult`, `levels`, evaluation helpers) and pure
  value objects from `app` (`session.MoveRecord`, `settings.GameSettings`,
  `analysis.GameReview`, `achievements.Achievement`, `keymap.BINDINGS`). It never imports
  `app.game`.
- `app.game` is the composition root: it may import anything. `ui.renderer` therefore has
  no cycle back into the controller.
- `cli` imports `app.game` and the small tables it prints.

The layering is enforced by review (and by `flake8`'s unused-import check keeping the
import lists honest). `scripts/check_imports.py` prints the cross-layer import graph if you
want to verify a change:

```bash
python scripts/check_imports.py
```

---

## core

### `core/constants.py`

Player ids, `DIRECTIONS` (8 `(dr, dc)` pairs), modes (`MODES`, `MODE_LABELS`,
`MODE_DESCRIPTIONS`), `SUPPORTED_BOARD_SIZES`, `DEFAULT_BOARD_SIZE`, and
`opponent(player)`.

### `core/bitboard.py`

| Symbol | Contract |
|---|---|
| `Geometry(size)` | Precomputed shift/mask tables for one size. `move_mask(own, opp)`, `flips(own, opp, bit)`, `spread(bits)`. Instances are cached by `geometry_for(size)` — never construct one directly in hot code. |
| `Position(size=8, black=None, white=None, turn=PLAYER_BLACK)` | Immutable position. Fields `black`, `white`, `turn`, `zobrist`. `legal_moves()` returns a **cached** mask; `apply(row, col)` / `apply_index(i)` return a new position and maintain the Zobrist hash incrementally. `pass_turn()` swaps the side to move without changing discs. `is_terminal()`, `result()` (winner, `0` for a draw, `None` if the game continues). |
| `iter_bits(mask)` | Yields set-bit indices, lowest first. |
| `mask_to_cells(mask, size)` | `[(row, col), …]` for a mask. |

Two properties everything else relies on:

1. **Runs are grown with an early-exit loop**, not a fixed number of doubling steps. A
   fixed count silently truncates long runs (this was a real bug: it broke perft at depth
   5). Do not "optimise" it back into a constant.
2. `Position.__eq__` covers size, both disc masks and the turn. Positions are unhashable
   by design; key dictionaries on `position.zobrist` instead.

### `core/board.py`

`Board` is the mutable, readable rules implementation the interface uses. `grid[row][col]`,
`current_player`, `game_over`, `winner`.

| Method | Notes |
|---|---|
| `is_valid_move(row, col, player)` | Bounds, emptiness and a flip in at least one direction. |
| `get_valid_moves(player)` / `legal_move_count(player)` | |
| `make_move(row, col, player)` | Mutates, returns the flipped cells, and **sets `current_player = opponent(player)`** — not `opponent(current_player)`. Replays and analysis walk a move log and must not depend on the board's own turn tracking. |
| `check_game_over()` | Resolves the end of the game, or passes the turn when only the side to move is stuck. Call it after every `make_move` in a replay. Returns True only when the game is freshly over. |
| `to_position()` / `load_position(position)` | Bridge to the bitboard world. `to_position()` sets the turn from `current_player`. |

`tests/test_bitboard.py::test_reference_and_bitboard_agree` fuzzes `Board` against
`Position` (legal moves *and* flip sets) on 6×6, 8×8 and 10×10 — any change to either
implementation must keep it passing.

### `core/notation.py`

`move_name(row, col)`, `OPENINGS`, `identify_opening(moves, size)` → `Opening | None`.
Names are matched against a prefix table, so a game keeps its name while it stays in the
book.

---

## ai

### `ai/levels.py`

`LEVELS` maps 1–5 to frozen `Level` records (`name`, `time_limit`, `max_depth`,
`endgame_empties`, `noise`, `use_book`, `is_random`, `description`). `get_level(n)` clamps.
Adding a level means adding an entry here, a row in the Options overlay and a row in the
README/AI_DESIGN tables.

### `ai/evaluation.py`

`evaluate(position, own_moves=None)` — static score from the side to move. Weights
interpolate between `OPENING_WEIGHTS` (≥48 empties) and `ENDGAME_WEIGHTS` (≤12); the
interpolated profile is **cached per empty count** because this runs at every leaf.
`corner_tables(geometry)` returns cached square tuples *and* their masks.
`terminal_score(own_discs, other_discs)` returns ±`TERMINAL_BONUS` plus 1000 per disc, so
any win beats any static advantage. `win_probability(position)` is the blended estimate
used by the evaluation bar; `evaluate_for_black()` re-orients the score.

### `ai/search.py`

| Symbol | Contract |
|---|---|
| `SearchLimits(time_limit, max_depth, endgame_empties, noise, node_limit)` | `time_limit=0` means "no deadline" (used by tests and `rank`). |
| `Searcher(size, table_limit, seed)` | Reusable searcher. `search(position, limits, progress=None) -> SearchResult`; `rank(position, depth) -> [(index, score), …]` best first; `hint(position, …)`; `clear()`; `cancel()`. |
| `SearchResult` | `index`, `score`, `depth`, `nodes`, `elapsed`, `pv`, `complete`; `move` and `pv_moves()` convert indices to `(row, col)`. |
| `square_priority(size)` | Static ordering table (corners 4000, X-squares −1200, C-squares −300, edges 320). |

Behaviour worth knowing:

- Iterative deepening always leaves a usable move; if an iteration is cut off the last
  completed depth (or the best root move seen so far) is used.
- `_IN_TREE_EXACT = 6` caps endgame extensions inside the tree; deeper exact solving
  happens at the root when `empties <= limits.endgame_empties` and there is time left.
  Without that cap a depth-1 iteration could never finish and the engine fell back to a
  statically ordered move (the bug that made Master lose to Expert).
- `WIN_THRESHOLD = 10_000_000` lets the search stop as soon as a forced win is proven.
- The clock is checked every 2048 nodes; a new iteration only starts if less than 55 % of
  the budget is gone.
- The transposition table stores `(depth, score, flag, move)` keyed by Zobrist and is
  cleared wholesale when it reaches `table_limit` (600 000 entries by default).

### `ai/endgame.py`

`solve(position, max_empties)` and `perfect_difference(position)` — a brute-force
reference solver used by tests to cross-check the search's endgame results. Slow by
design; never call it from the game loop.

### `ai/book.py`

`OpeningBook.load(size)` reads `ai/data/opening_book.json`, **replays every line** and
skips (with a warning) any that is illegal. `lookup(move_log)` returns the book reply,
`name_for(move_log)` the opening name.

### `ai/engine.py`

`Engine(difficulty=2, size=8, seed=None)` is the facade the app uses.

| Method | Notes |
|---|---|
| `get_move(board)` | Honours the level: random, book, or search. Never returns `None` when a move exists. |
| `quick_hint(board)` | Depth-1 ranking on a **separate** searcher — cheap enough to call after every move. |
| `get_hint(board, time_limit)` | Timed search on the hint searcher. |
| `analyse_limits(board, limits, progress)` | Explicit search on the main searcher (used by the hint worker). |
| `record_move` / `reset_log` / `move_log` | The engine's own copy of the move log, used by the book. |
| `resize(size)` | Rebuilds both searchers and reloads the book. Called automatically by `_position_for`. |
| `opening_name()`, `evaluate()`, `evaluate_for_black()`, `win_probability()` | Convenience wrappers. |

`_position_for(board)` accepts a `Board` or a `Position` and **auto-resizes** when the
geometry differs, so a caller can never hand the engine a position of the wrong size.

### `ai/worker.py`

`SearchWorker` runs one search at a time on a daemon thread. `start(engine, board,
limits)`, `poll() -> (progress, final)`, `take_result()`, `cancel()` (joins for ≤0.5 s).
`cancel()` also **clears any pending result**, so a cancelled search can never be applied
to a different position.

---

## ui

Pure-ish rendering: `ui/theme.py` holds only data (no pygame import); the rest draw.

| Module | Key API |
|---|---|
| `ui/layout.py` | `Rect` (sequence protocol so pygame accepts it), `Layout`, `compute_layout(size, board_size, ui_scale)`, `clamp_window`, `MIN_UI_SCALE = 0.75`, `MAX_UI_SCALE = 1.5`. |
| `ui/assets.py` | `FontBook` (cached text surfaces, `measure`, `fit`), `DiscCache` (3× supersampled sprites), `TextureCache`, `shade`, `mix`, `icon()`. |
| `ui/drawing.py` | Primitives: `gradient` (cached), `draw_panel`, `draw_shadow`, `draw_bevel`, `draw_ring`, `draw_glow`, `draw_star`, `draw_diamond`, `draw_checker`, `draw_bar`, `draw_separator`, `draw_text`, `draw_label_value`, `fit_text`, `wrap_text`, `with_alpha`. |
| `ui/animation.py` | `AnimatedValue`, `AnimationManager`, `ParticleSystem`, `ScreenShake`, `ToastStack`, easing functions. |
| `ui/widgets.py` | `Button`, `draw_segmented`, `draw_toggle`, `draw_slider`, `draw_tabs`, `draw_badge`, `draw_tooltip`, `draw_keycap`, `draw_scrollbar`, `focus_ring`. |
| `ui/hud.py` | `build_menubar`, `draw_status`, `StatusData`, `format_clock`. |
| `ui/sidebar.py` | `draw_sidebar`, `SidebarData`, `SidebarHit`, `LABEL_COLORS`. |
| `ui/overlays.py` | `draw_options`, `draw_help`, `draw_stats`, `draw_game_over`, `draw_resume`, plus their `*Data` payloads and `OPTION_TABS`. Every interactive element appends a `ClickTarget`. |
| `ui/renderer.py` | `Renderer` — owns the display surface, caches the board plate and disc sprites, composes a frame from a `RenderModel`, and exposes `targets` (click targets, hit-tested in reverse) plus `menu_bar_buttons`. |

Rules for the renderer:

- `Renderer.draw(model)` composes and **flips** the display; call it once per frame.
- `Renderer.targets` is rebuilt every frame. The controller hit-tests it, so any new
  clickable element must append a `ClickTarget(action, value)`.
- Score values are `AnimatedValue`s: call `animate_move(record)` after a move or
  `sync_scores(black, white)` to jump.
- Adding a theme means adding a `Theme` entry to `THEMES`, a key to `THEME_ORDER`, and
  (if it has special markers) a `marker_style`.

---

## app

### `app/session.py`

`Session` owns the board, the records, undo/redo and the clocks; it contains no pygame.

| Member | Notes |
|---|---|
| `apply_move(row, col, now=None)` | Raises `IllegalMoveError` for illegal input, snapshots for undo, appends a `MoveRecord`, updates clocks and opening name, bumps `revision`. |
| `records` / `ply` / `move_count` | The authoritative move list (used to save and to review). |
| `revision` | Increments on every mutation. Anything caching a *view* of the session (the review board cache, for example) keys on it. |
| `undo()` / `redo()` / `can_undo()` / `can_redo()` | Unlimited; snapshots include the clock state. |
| `position_at(ply)` | Replays to a ply and returns a `Board` — the review screen shows this. |
| `play_pending_pass()` | Applies a pass when the side to move is stuck. |
| `finish_on_time()` | Ends the game when a clock flags; returns the player who ran out. |
| `clock` | `ClockState` with `mode`, `base`, `increment`, `elapsed`, `moves`; `remaining()`, `flagged()`. |

`MoveRecord` carries `player`, `row`, `col`, `flips`, `ply`, both disc counts,
`probability_black` (for the graph) and `passed_next` (so the UI can toast a pass).

### `app/game.py`

`Game(LaunchOptions)` is the controller; `LaunchOptions` mirrors the CLI. Structure:

- `handle_events()` → `on_click` / `on_key` → `_dispatch_target` / binding table.
- `update(dt)` → poll workers (`_poll_search`, `_poll_hint`, `_poll_review`), tick the
  clock and the replay timer, then `_maybe_start_ai()`.
- `draw()` → build a `RenderModel` (`_build_model`) and hand it to the renderer.

Stale-result protection: `_position_key()` returns `(size, zobrist)`. Every search and
hint records the key it was started for and the result is dropped if the key changed in
the meantime. Keep that guard on any new asynchronous work.

Review caching: `_review_cache` holds `((ply, revision, size), Board)` so stepping through
a review does not replay the move list 60 times a second.

`REVIEW_DEPTH` lives in `app/analysis.py` and is the single source of truth for review
depth; the controller imports it.

### `app/settings.py`

`GameSettings` (19 fields, `validated()` clamps everything, `from_dict`/`from_legacy`
migrate), `GameStats` (totals, per-level `LevelRecord`s, achievements) and
`GameSummary` (facts about one finished game).

### `app/persistence.py`

| Function | Contract |
|---|---|
| `atomic_write_json(path, payload)` | Temp file in the same directory, `fsync`, `os.replace`. |
| `load_settings` / `save_settings` | Schema 2, migrates v3 files written next to the source tree. |
| `load_stats` / `save_stats` | Schema 2, tolerant of missing keys; a corrupt file starts fresh with a warning. |
| `load_game` / `save_game_file` / `build_save_payload` | Schema 4 (v3 migration). **Every** malformed field raises `SaveFileError` — missing keys, non-numeric values, malformed blocks, unsupported board sizes, and a schema newer than `SAVE_SCHEMA` — and every move is replayed for legality before the file is accepted. |
| `SavedGame` | `board_size`, `mode`, `level`, `player_color`, `moves`, `game_over`, `winner`, `clocks`; `replay()` rebuilds the board, `clock_elapsed()` validates the clock block. |

Keep the rule: user-editable JSON is parsed defensively, and nothing that fails to parse
may ever reach `Session`.

### `app/analysis.py`

`analyse_moves(moves, size=8, depth=REVIEW_DEPTH, progress=None, should_stop=None)`
replays the game and, for every ply, ranks all legal moves with `Searcher.rank` at a fixed
depth. `loss` is the drop in win probability (percentage points) between the best move and
the played one; `classify(loss)` maps it to `Best/Good/Inaccuracy/Mistake/Blunder`.
`GameReview` exposes `accuracy(player)`, `counts(player)`, `worst(player, limit)`,
`assessment_for(ply)` and `summary()`. `ReviewWorker` runs it on a daemon thread;
`cancel()` is honoured between plies.

### `app/keymap.py`

`BINDINGS` is the single table behind dispatch, the help overlay and the Options → Controls
tab. A `Binding` has `keys`, `action`, `label`, `display`, `context` (`GLOBAL`, `PLAYING`,
`REPLAY`, `AI_VS_AI`) and optional `modifiers`. Modifier bindings win over plain ones, and
plain bindings never fire while Ctrl/Alt/Meta is held.

### `app/audio.py`

`SoundBank(enabled, volume)` synthesises ten 16-bit stereo effects at 44.1 kHz with
`array('h')` buffers. `play(name, variant=0)` (four "flip" variants), `set_volume`,
`set_enabled`, `shutdown`. Missing audio devices degrade to silence, never to an
exception.

### `app/paths.py`

`data_dir()`, `settings_path()`, `stats_path()`, `autosave_path()`, `save_path(name)`,
`log_path()`, `legacy_candidates(filename)`, `find_existing(...)`. Honours
`IAGO_DATA_DIR`, `XDG_DATA_HOME`, `APPDATA` and `Application Support`; the override is a
*base* directory (`<base>/iago`).

### `app/achievements.py`

`ACHIEVEMENTS` (eleven), `evaluate(stats, summary) -> [Achievement]`, `progress(stats)`.
Predicates are pure functions of the statistics plus the finished game's `GameSummary`.

### `cli.py`, `__main__.py`, `main.py`

`build_parser()` and `main(argv)` — the only place that constructs a `Game`. `main()`
returns an exit code (0 ok, 2 for "no window"/config errors). `main.py` is a thin shim for
people used to the old layout.

---

## util

`util/log.py` — `configure(verbose, quiet, log_file)` (console + rotating file, 512 KB × 3)
and `get_logger(name)` returning `iago.<name>`. Importing the module configures a console
handler once.

`util/errors.py` — the whole exception taxonomy. Six classes; the two bases exist so
callers can catch a family rather than enumerating leaves:

| Error | Raised when |
|---|---|
| `IagoError` | Base class; anything the UI can show as a toast. |
| `BoardError` | A board operation was invalid (base of `IllegalMoveError`). |
| `IllegalMoveError` | A move is not legal for the side to move. |
| `PersistenceError` | Base class for storage problems. |
| `SettingsError` | Settings could not be written. |
| `SaveFileError` | A save is missing, unreadable, not JSON, malformed, from a newer schema, or does not describe a legal game. |

Statistics failures are logged and swallowed on purpose — losing a statistics write must
never interrupt a game. The search keeps a private `SearchTimeout` that never leaves
`ai/search.py`.

---

## Invariants to preserve

1. **`Board` and `Position` agree.** Legal moves and flip sets must match for every
   position; the fuzz test is the guard.
2. **Scores come from the side to move; UI probabilities come from Black.**
3. **Turns follow the mover.** `Board.make_move` sets `current_player = opponent(player)`;
   `Position._apply_bit` does the same.
4. **Never apply a stale search.** Guard asynchronous results with `_position_key()`.
5. **Sessions mutate → bump `revision`.** Anything caching a derived board must key on it.
6. **The engine resizes itself** (`_position_for`), so call sites may pass any size.
7. **User JSON is untrusted.** Parse defensively; raise `SaveFileError`/`SettingsError`,
   never `KeyError`/`ValueError` at the UI boundary.
8. **Theme data stays pure.** `ui/theme.py` must not import pygame, so it can be tested
   without a display.
9. **One search at a time per worker**, and `cancel()` invalidates pending results.
10. **The keymap is the single source of truth** for shortcuts, the help overlay and the
    Controls tab.

---

## Extension recipes

**Add a theme.** Append a `Theme(...)` to `ui/theme.py`, add the key to `THEME_ORDER`, then
regenerate the screenshots (`python scripts/generate_screenshots.py`). If the markers need
to differ, set `marker_style`.

**Add a difficulty level.** Extend `LEVELS` in `ai/levels.py` and `MAX_DIFFICULTY`, add the
row to the Options overlay's level segmented control and to the README/AI_DESIGN tables,
then validate with `python scripts/selfplay.py --a <new> --b <previous> --games 6`.

**Add an achievement.** Append an `Achievement(key, title, description)` to
`ACHIEVEMENTS` with an `unlock(...)` condition, add the row to the user guide, and add a
test in `tests/test_settings.py` (which covers achievements) that asserts it unlocks once
and never twice.

**Add a key binding.** Add a `Binding` to `BINDINGS` with a context, add the action to
`Game.on_key`'s dispatch table, and the help overlay plus the Controls tab pick it up
automatically.

**Add an option.** Add the field to `GameSettings` (validated range included), a control in
the relevant `draw_options` tab with a `ClickTarget`, and a handler branch in
`Game._dispatch_target`/`_toggle_setting`. Persisted automatically.

**Add a widget.** Put it in `ui/widgets.py` taking `(surface, fonts, theme, rect, …)` and
returning the rectangle the controller should hit-test.

---

## Error taxonomy

The UI shows `IagoError` messages as toasts (`Game._warn`) and logs everything else. A new
failure mode that a player could trigger belongs in `util/errors.py`; anything else is a
bug and should be fixed rather than caught.

---

## Testing map

| Area | File |
|---|---|
| Rules, fuzz vs bitboard, perft | `tests/test_bitboard.py`, `test_board.py` |
| Evaluation, levels, engine facade, book | `tests/test_ai.py` |
| Search, TT, endgame cross-checks | `tests/test_search.py` |
| Notation and openings | `tests/test_notation.py` |
| Session state, undo/redo, clocks | `tests/test_session.py` |
| Review and ratings | `tests/test_analysis.py` |
| Settings, statistics and achievements | `tests/test_settings.py` |
| Persistence, schema migration, malformed input | `tests/test_persistence.py` |
| Path resolution per platform | `tests/test_paths.py` |
| Themes, layout, widgets, drawing | `tests/test_ui.py` |
| Renderer and hit targets | `tests/test_render.py` |
| Audio synthesis | `tests/test_audio.py` |
| Controller end-to-end, CLI | `tests/test_controller.py`, `test_cli.py` |

Run everything with `pytest -q`: 414 tests, about 25 s, entirely headless. The suite is the
specification for anything documented here.
