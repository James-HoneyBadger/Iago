# Development

- [Setup](#setup)
- [Commands](#commands)
- [Layout of a change](#layout-of-a-change)
- [Adding a theme](#adding-a-theme)
- [Adding a difficulty level](#adding-a-difficulty-level)
- [Adding a key binding](#adding-a-key-binding)
- [Adding an overlay](#adding-an-overlay)
- [Regenerating assets](#regenerating-assets)
- [Profiling](#profiling)
- [Release checklist](#release-checklist)

---

## Setup

```bash
git clone https://github.com/James-HoneyBadger/Iago_Deluxe.git
cd Iago_Deluxe
./setup.sh
```

`setup.sh` creates `.venv`, installs the package in editable mode with the `dev` extra,
and runs the test suite. Afterwards:

```bash
.venv/bin/python -m iago        # play
.venv/bin/iago --help           # CLI
```

Pre-commit hooks (black, flake8, mypy and a few hygiene checks) are configured in
`.pre-commit-config.yaml`:

```bash
.venv/bin/pip install pre-commit && .venv/bin/pre-commit install
```

---

## Commands

| Command | Purpose |
|---|---|
| `pytest -q` | the whole suite (330 tests, ~15 s, headless) |
| `pytest tests/test_search.py -q` | one module |
| `pytest --cov --cov-report=term-missing` | coverage |
| `black src tests scripts main.py` | format |
| `flake8 src tests scripts main.py` | lint |
| `mypy src/iago` | types |
| `pylint src/iago` | static analysis |
| `python scripts/bench_search.py` | throughput and depth benchmarks |
| `python scripts/selfplay.py --a 5 --b 4 --games 6` | strength validation |
| `python scripts/build_book.py` | regenerate the opening book |
| `python scripts/generate_screenshots.py` | regenerate `docs/images/` |
| `python -m build` | build sdist + wheel |

The suite runs headless: `tests/conftest.py` sets `SDL_VIDEODRIVER=dummy`,
`SDL_AUDIODRIVER=dummy` and points `IAGO_DATA_DIR` at a temporary directory, so tests
never touch your real settings or statistics.

---

## Layout of a change

The layers are described in [ARCHITECTURE.md](ARCHITECTURE.md). In practice:

* **Rules** live in `core/board.py` (reference) and `core/bitboard.py` (fast). Change
  both, then extend the fuzz test — it will tell you if they disagree.
* **Engine changes** belong in `ai/`. Anything that affects move choice should come with a
  test in `tests/test_search.py` and a benchmark note in `docs/AI_DESIGN.md`.
* **Visual changes** belong in `ui/`. Themes are pure data; widgets take explicit colours
  and return rectangles for hit testing.
* **Behaviour** (commands, state transitions) belongs in `app/game.py`, with the model in
  `app/session.py`.

---

## Adding a theme

1. Add a `Theme(...)` instance in `src/iago/ui/theme.py`, copying an existing one.
2. Register it in the `THEMES` tuple inside that module.
3. Run `pytest tests/test_ui.py tests/test_render.py` — the tests check every theme for
   required fields and render it headlessly.
4. Optionally regenerate the screenshots:

   ```bash
   python scripts/generate_screenshots.py
   ```

5. Add the key to the theme list in `docs/USER_GUIDE.md` and the README table.

The `Theme` dataclass is frozen, so a missing new field is a type error, not a runtime
surprise.

---

## Adding a difficulty level

1. Append a `Level` to `LEVELS` in `src/iago/ai/levels.py` with a unique `number`.
2. `MAX_DIFFICULTY` and the UI’s segmented control update automatically.
3. Extend the keymap range if you want a direct number shortcut
   (`Binding((pg.K_1, …, pg.K_5), …)`).
4. Validate it:

   ```bash
   python scripts/selfplay.py --a 6 --b 5 --games 6 --time-scale 0.2
   ```

5. Document the measured result in `docs/AI_DESIGN.md` and the README table.

---

## Adding a key binding

All bindings live in `src/iago/app/keymap.py`. Adding one entry updates the help overlay,
the Controls tab, the CLI `--list-controls` output and the controller dispatch:

```python
Binding((pg.K_g,), "toggle_grid", "Show/hide grid", "G", PLAYING),
```

Then handle the action in the dispatch table in `Game.on_key`.

Bindings with modifiers take precedence (`Ctrl+S` beats `S`), and a plain binding never
fires while Ctrl/Alt/Meta is held.

---

## Adding an overlay

1. Draw the content in `src/iago/ui/overlays.py` and return a list of `ClickTarget`s.
2. Add a branch to `Renderer._draw_overlay`.
3. Open it from the controller with `self.overlay = "yourname"` and handle the action
   strings in `Game._dispatch_target`.
4. Test it in `tests/test_render.py` (renders and registers targets) and, if it changes
   game state, in `tests/test_controller.py`.

---

## Regenerating assets

| Asset | Script | Notes |
|---|---|---|
| Opening book | `scripts/build_book.py` | Ranks replies at depth 4; lines are validated on load |
| Screenshots | `scripts/generate_screenshots.py` | Renders real frames headlessly; commit the PNGs |
| Window icon | generated at runtime from the active theme | no asset needed |
| Sounds | synthesised at start-up | no asset needed |

There are **no binary assets** in the repository other than the documentation screenshots.

---

## Profiling

The engine is where the time goes. Useful starting points:

```bash
# Where does the search spend its time?
.venv/bin/python -m cProfile -s cumtime scripts/bench_search.py | head -40

# Line-level timings (needs line_profiler)
.venv/bin/python -m pip install line_profiler
# then decorate Searcher._negamax / Geometry.move_mask with @profile
```

Known hot spots, in order: `Geometry.move_mask`, `Position.apply` (flips + hashing),
`evaluate`, and list sorting in `Searcher._order`. Anything that reduces big-integer
shifts per node or nodes per move moves the needle.

---

## Release checklist

1. `black --check`, `flake8`, `mypy`, `pylint` clean.
2. `pytest -q` green on Linux (CI covers macOS and Windows).
3. `python scripts/bench_search.py` and the self-play matches re-run; update the numbers
   in `docs/AI_DESIGN.md` if they moved materially.
4. `python scripts/generate_screenshots.py` to refresh `docs/images/`.
5. Bump `VERSION` in `src/iago/branding.py` and `pyproject.toml`, and add a
   `docs/CHANGELOG.md` entry.
6. `python -m build` and install the wheel in a clean venv; run `iago --version` and start
   one game.
