# Architecture

How Iago is put together, and why.

- [Layers](#layers)
- [Module map](#module-map)
- [Data flow](#data-flow)
- [The controller state machine](#the-controller-state-machine)
- [Threading model](#threading-model)
- [Rendering pipeline](#rendering-pipeline)
- [Layout maths](#layout-maths)
- [Persistence](#persistence)
- [Error handling and logging](#error-handling-and-logging)
- [Testing strategy](#testing-strategy)

---

## Layers

Iago is a four-layer application with a hard rule: **dependencies point downwards**.

```
┌──────────────────────────────────────────────────────────────┐
│ app   controller · session · settings · persistence · audio  │
│       analysis · keymap · achievements · paths               │
├──────────────────────────────────────────────────────────────┤
│ ui    theme · layout · assets · drawing · animation          │
│       widgets · hud · sidebar · overlays · renderer          │
├──────────────────────────────────────────────────────────────┤
│ ai    evaluation · search · endgame · book · levels · worker │
├──────────────────────────────────────────────────────────────┤
│ core  constants · bitboard · board · notation                │
└──────────────────────────────────────────────────────────────┘
                                   util: logging · errors
```

- `core` imports nothing from the project except `util`.
- `ai` imports `core` only.
- `ui` imports `core` and small value objects from `app` (settings, session records,
  analysis results) but never the controller.
- `app` imports everything; `renderer` never imports `app.game`, so there is no cycle.

The one deliberate exception is `app.game` → `ui.renderer`, which is the composition
root.

---

## Module map

| Module | Responsibility | Notable contents |
|---|---|---|
| `core/constants.py` | Player ids, directions, modes, supported board sizes | `PLAYER_BLACK`, `MODES`, `opponent()` |
| `core/bitboard.py` | Immutable bitboard position | `Geometry` (mask/shift tables), `Position`, Zobrist hashing |
| `core/board.py` | Reference list-based rules used by the UI | `Board` — validation, flips, pass handling, scoring |
| `core/notation.py` | Algebraic notation and opening names | `move_name`, `identify_opening`, `OPENINGS` |
| `ai/levels.py` | Difficulty presets | `LEVELS`, `Level` |
| `ai/evaluation.py` | Phase-interpolated static evaluation | weight profiles, stability, `win_probability` |
| `ai/search.py` | Alpha-beta search | `Searcher`, `SearchLimits`, `SearchResult`, `square_priority` |
| `ai/endgame.py` | Exact solving helpers | `solve`, `perfect_difference` (reference solver) |
| `ai/book.py` | Opening book loading and lookup | `OpeningBook`, `BookLine` |
| `ai/engine.py` | Public facade | `Engine` (alias `AI`) |
| `ai/worker.py` | Background search | `SearchWorker` |
| `ui/theme.py` | Colour themes (pure data) | `Theme`, `THEMES`, `get_theme` |
| `ui/layout.py` | Responsive geometry | `Rect`, `Layout`, `compute_layout` |
| `ui/assets.py` | Fonts, disc sprites, textures | `FontBook`, `DiscCache`, `TextureCache` |
| `ui/drawing.py` | Drawing primitives | gradients, panels, bars, glow, text |
| `ui/animation.py` | Easing, timelines, particles, toasts | `AnimationManager`, `ParticleSystem`, `ToastStack` |
| `ui/widgets.py` | Reusable controls | `Button`, `draw_segmented`, sliders, tabs |
| `ui/hud.py` | Menu bar and status panel | `build_menubar`, `draw_status`, `StatusData` |
| `ui/sidebar.py` | Move list and evaluation graph | `draw_sidebar`, `SidebarData` |
| `ui/overlays.py` | Modal screens | `draw_options`, `draw_help`, `draw_stats`, `draw_game_over` |
| `ui/renderer.py` | Frame composition and hit testing | `Renderer`, `RenderModel`, `ClickTarget` |
| `app/session.py` | The game model | `Session`, `MoveRecord`, `ClockState`, `Snapshot` |
| `app/game.py` | Controller | `Game`, `LaunchOptions` |
| `app/settings.py` | Persisted preferences and statistics | `GameSettings`, `GameStats`, `LevelRecord` |
| `app/persistence.py` | Versioned JSON storage | `SavedGame`, load/save functions, migrations |
| `app/audio.py` | Synthesised sound | `SoundBank`, `synthesize` |
| `app/analysis.py` | Post-game review | `analyse_moves`, `GameReview`, `ReviewWorker` |
| `app/keymap.py` | Single source of truth for bindings | `BINDINGS`, `lookup` |
| `app/achievements.py` | Unlock rules | `ACHIEVEMENTS`, `evaluate` |
| `app/paths.py` | Platform data directories | `data_dir`, `save_path` |
| `util/log.py`, `util/errors.py` | Logging and exceptions | `configure`, `IagoError` and friends |

---

## Data flow

```
          input                        model                     output
 ┌───────────────────┐       ┌────────────────────┐      ┌────────────────────┐
 │ pygame events     │──────▶│ Game (controller)  │─────▶│ RenderModel        │
 │ mouse / keyboard  │       │  · routing         │      │  · session         │
 └───────────────────┘       │  · state machine   │      │  · theme, overlays │
                             │  · commands        │      │  · thinking        │
 ┌───────────────────┐       └───────┬────────────┘      └─────────┬──────────┘
 │ SearchWorker      │◀──────────────┘                             │
 │ (thread)          │  SearchLimits          Renderer ────────────┘
 └─────────┬─────────┘                              │
           │ SearchResult                           ▼
           └──────────────▶ Game ──▶ Session ──▶ pygame.Surface
                                     │
                                     ├──▶ persistence (JSON)
                                     ├──▶ GameStats / achievements
                                     └──▶ ReviewWorker ──▶ GameReview
```

`Session` is the single source of truth for the position, history and clocks. The
controller never mutates the board directly; it asks the session, which raises
`IllegalMoveError` for anything invalid.

---

## The controller state machine

The overlay field is the state; there is no separate enum, which keeps transitions
explicit and local:

| State | Entered by | Exits to |
|---|---|---|
| `None` (playing) | start, close overlay | options, help, stats, gameover, resume |
| `options` | **O**, Options button | playing (close) or new game |
| `help` | **F1** | playing |
| `stats` | Stats button, **F1**→stats | playing |
| `gameover` | end of game, **A** | playing (rematch / close), review position |
| `resume` | autosave detected at start-up | playing (resume / discard) |

Separately, `selected_ply` switches the board into review mode (a historical position is
rendered from `session.position_at(ply)`), and `replay_active` advances it on a timer.
Both are orthogonal to the overlay state.

Commands (new game, undo, theme, save…) are plain methods on `Game`; the keymap and the
click targets both dispatch through the same table.

---

## Threading model

```
main thread                                  search thread
───────────                                  ─────────────
loop: events → update → draw                 engine.analyse_limits(position, limits)
   │                                              │
   ├─ worker.start(engine, board, limits) ───────▶│  _negamax ...
   ├─ worker.poll() → (progress, final)           │  progress callback every depth
   ├─ render "Thinking… depth 9 · 58k nps"        │
   └─ on final: apply the move                    ▼
                                             SearchResult (immutable)
```

* `SearchWorker` runs at most one search at a time. `start()` cancels and joins any
  previous thread first, so the shared transposition table is never touched from two
  threads.
* `Engine.cancel_search()` sets a flag that `_negamax` checks every 2048 nodes, so a
  cancelled search exits within microseconds.
* The worker only publishes immutable `SearchResult` objects — it never touches pygame.
* Python's GIL means the search and the interface share one core. `sys.setswitchinterval(0.002)`
  is set at start-up so the interface is scheduled frequently enough to keep painting and
  animating while the engine thinks.

A second worker (`hint_worker`) serves on-demand hints, and `ReviewWorker` analyses a
finished game. Both use their own `Searcher` instances, so they never contend for the
engine's table.

---

## Rendering pipeline

```
Renderer.draw(model)
  ├─ background gradient (cached per theme + size)
  ├─ menu bar            (cached gradient, Button widgets)
  ├─ board plate         (cached Surface: frame + checker + texture + grid + coordinates)
  │    ├─ last-move ring (pulsing)
  │    ├─ hover tint     (cells that would flip)
  │    ├─ discs          (cached supersampled sprites, optional flip/place animation)
  │    ├─ move markers   (dots or shapes, star for the hint)
  │    └─ particles
  ├─ sidebar             (opening, evaluation graph, move rows, scrollbar)
  ├─ status panel        (score, turn, clocks, evaluation bar, thinking readout)
  ├─ toasts
  ├─ debug overlay       (F3)
  ├─ modal overlay       (options / help / stats / game over / resume)
  └─ tooltips  →  display.flip()
```

### Caching strategy

| Cache | Key | Invalidated by |
|---|---|---|
| Board plate | theme, cell size, board size, coordinates flag | theme/size/scale change |
| Background | theme, window size | resize, theme change |
| Disc sprites | theme, player, radius (± alpha) | theme change |
| Text surfaces | text, role, colour, bold | font scale change |
| Gradients | size, colours | never (LRU-ish, small) |

Disc sprites are drawn at 3× and smoothed down, which gives clean anti-aliasing without
any dependency beyond pygame. A 60 px cell therefore costs one blit per disc.

### Animation

`AnimationManager` maps keys (`("place", row, col)`, `("flip", row, col)`) to a
`Timeline`. A move registers a placement with `ease_out_back` and one flip per captured
disc, delayed by 50 ms per Manhattan step — the ripple. During a flip the renderer
squashes the disc horizontally (`|cos(πp)|`) and swaps the colour at the halfway point,
which reads as a real 3-D flip.

---

## Layout maths

`compute_layout(window, board_size, ui_scale)` is a pure function returning a frozen
`Layout`:

1. Clamp the window to `MIN_WINDOW`…`MAX_WINDOW`.
2. Reserve the menu bar (`46 px`), status panel (`132 px`), gutters (`16 px`) and the
   frame (`10 px`), all multiplied by the UI scale.
3. Show the sidebar only when the window is at least `1024 px` wide (scaled).
4. `cell = clamp(min(available_w, available_h) // board_size, 26, 96)`.
5. Centre the framed board in the remaining space; the sidebar takes the rest.

Because the function is pure, the tests assert invariants for window sizes from 760×660
to 2400×1800 across 6×6, 8×8 and 10×10 boards, and `Layout.hit_cell` round-trips
`cell_center` exactly.

---

## Persistence

All writes go through `atomic_write_json` (temporary file in the same directory,
`fsync`, then `os.replace`), so a crash mid-write can never corrupt a save. Reads are
validated:

* settings and statistics are coerced into range, unknown keys ignored;
* saved games are **replayed against the real rules** — an illegal move in the file is
  rejected with the offending move named.

Legacy files are migrated on first read (see [SAVE_FORMAT.md](SAVE_FORMAT.md)).

---

## Error handling and logging

* Every deliberate failure raises a subclass of `IagoError` (`BoardError`,
  `IllegalMoveError`, `AIError`, `SaveFileError`, …). The controller catches
  `IagoError`, shows a toast and logs it; programming errors are not swallowed.
* Logging is configured once from the CLI: console at INFO (or DEBUG with `--verbose`)
  and a rotating file handler in the data directory.
* Background threads log unexpected exceptions with a traceback and degrade gracefully
  (a failed search returns `SearchResult(index=None)`).

---

## Testing strategy

330 tests, all headless (`SDL_VIDEODRIVER=dummy`), run in ~15 s.

| Area | Approach |
|---|---|
| Rules | Direct unit tests plus random-game fuzzing |
| Bitboard | Equivalence with the reference board over random games at 6/8/10; published perft counts (4, 12, 56, 244, 1396, 8200) |
| Search | Legal-move guarantee, determinism at fixed depth, TT-independence, perfect endgame play, brute-force cross-check of the exact solver |
| Engine | Book legality, level monotonicity, hint validity |
| Persistence | Round-trips, corrupt files, legacy migration, atomicity |
| UI | Layout invariants, theme completeness, widget geometry, easing bounds |
| Rendering | Every theme × board size × overlay rendered headlessly; hit targets verified |
| Controller | Scripted games: human move → engine reply, paired undo, save/load, clock flag, review selection |
