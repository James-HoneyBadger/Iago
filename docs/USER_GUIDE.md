# Iago — User Guide

Everything the game can do, screen by screen.

- [Starting the game](#starting-the-game)
- [The window](#the-window)
- [Playing](#playing)
- [Game modes](#game-modes)
- [Difficulty](#difficulty)
- [Hints and analysis](#hints-and-analysis)
- [Options](#options)
- [Statistics and achievements](#statistics-and-achievements)
- [Post-game review](#post-game-review)
- [Clocks](#clocks)
- [Saving, loading and resuming](#saving-loading-and-resuming)
- [Keyboard reference](#keyboard-reference)
- [Command line](#command-line)
- [Troubleshooting](#troubleshooting)

---

## Starting the game

```bash
./play.sh                 # sets everything up on first run, then launches
```

Other ways to start it:

```bash
.venv/bin/python -m iago      # module entry point
.venv/bin/iago                # installed console script
python main.py                # compatibility shim
```

The first launch creates a virtual environment, installs `pygame-ce` and starts the
game. Subsequent launches are immediate.

---

## The window

![Iago, Classic theme](images/board-classic.png)

| Area | What it shows |
|---|---|
| **Menu bar** (top) | New Game · Undo · Redo · Hint · Options · Help, plus your saved record |
| **Board** | The 6×6, 8×8 or 10×10 grid, framed in wood, with coordinates on the edges |
| **Sidebar** (wide windows) | Opening name, evaluation graph, full move list, hint line |
| **Status bar** (bottom) | Disc counts, mode, difficulty, whose turn it is, clocks, win probability |
| **Overlays** | Options, Controls, Statistics, Game over and Resume prompts |

The layout is responsive. Narrow the window and the sidebar folds away; resize freely,
press **F11** for fullscreen, and use **Appearance → Interface scale** if everything is
too small or too large.

### Board furniture

- **Dots** — legal moves for the side to move.
- **★ gold star** — the engine's suggested move (computed instantly after each move).
- **Gold ring** — the square played last; it pulses gently.
- **Tinted squares** — the discs that would flip if you played the square under the
  cursor.
- **Ghost disc** — a translucent preview of the disc you are about to place.
- **High Contrast theme** replaces dots and stars with a hollow square and a diamond, so
  the markers stay distinguishable without relying on colour.

---

## Playing

1. Click any square marked with a dot. The disc is placed, captured discs flip outward
   from the square, and play passes to the other side.
2. If a side has no legal move, the turn is passed automatically and a toast tells you
   so.
3. The game ends when neither side can move. The result panel shows the winner and the
   final disc count.

Illegal clicks are rejected with a short buzz and a small shake — nothing changes on the
board.

### Undo and redo

**U** (or **Ctrl+Z**) steps back one *round* when you play against the engine: it undoes
the engine's reply as well as your move, so you are always returned to your own turn.
**Y** redoes one move at a time. Undo and redo are unlimited and also restore the clocks.

---

## Game modes

| Mode | Description |
|---|---|
| **Human vs AI** | You against the engine. Choose your colour in Options. |
| **2-Player** | Two humans share the keyboard and mouse. |
| **AI vs AI** | Watch two engines play. **P** pauses, **+**/**-** change the speed (Instant → Slow). |

Switch modes with **M** or from **Options → Game**. Changing the mode starts a new game.

---

## Difficulty

| Level | Name | Thinking time | What it does |
|---|---|---|---|
| 1 | Easy | instant | Plays a random legal move. |
| 2 | Medium | instant | One-ply look-ahead with deliberate noise — beatable but not silly. |
| 3 | Hard | 0.6 s | Full alpha-beta search plus the opening book. |
| 4 | Expert | 2.5 s | Transposition table, deeper search, exact endgame solving. |
| 5 | Master | 5 s | Tournament settings; solves more of the endgame perfectly. |

Change it with **D** (cycle), **1**–**5** (direct) or Options. Changing difficulty applies
immediately, even mid-game.

While the engine thinks, the status bar shows its live search depth, node count and
nodes per second, and the window stays fully responsive — you can resize it, open
Options, or press Undo to abandon the search.

---

## Hints and analysis

- **H** toggles the move markers (dots and star).
- **Space** asks the engine for a stronger suggestion; the result appears as the gold
  star and in the sidebar as `Hint: c4`.
- **A** (after the game ends, or any time) runs a full review of the game.

---

## Options

![Options](images/options.png)

**Game**
- Mode, difficulty, colour, board size (6×6 / 8×8 / 10×10) and clock.
- Changing mode, colour or board size starts a new game.

**Appearance**
- Theme grid (Classic, Walnut, Ocean, Sunset, Forest, Midnight, High Contrast).
- Toggles for animations, particles, board coordinates and the evaluation bar.
- Interface scale slider (0.75× – 1.5×).

**Audio**
- Sound on/off, volume slider and a test button.

**Controls**
- A complete, always-current list of key bindings (the same table the controller uses).

---

## Statistics and achievements

![Statistics](images/statistics.png)

- Totals: games, wins, win rate, best score and best winning streak.
- A per-difficulty table with a win-rate bar.
- Achievements, unlocked as you play: **First Blood**, **Seasoned**, **Giant Slayer**
  (beat Master), **Flawless** (hold every square), **Clean Sheet**, **Against the Odds**
  (win from under 15% winning chances), **On Fire** (five wins in a row), **Blitz**,
  **To the Last Disc**, **Devoted** and **Grand Slam** (beat every level).

Statistics are recorded for Human vs AI games and persist between sessions. Newly
unlocked achievements appear as toasts at the end of a game.

---

## Post-game review

![Game over and review](images/game-over.png)

When a game ends, the result panel shows the score, the number of moves, the elapsed
time and the mode. It then analyses the game in the background:

- **Accuracy** for both sides (0–100%).
- Counts of **blunders**, **mistakes** and **inaccuracies**.
- **Key moments**: the three costliest moves, with the move that should have been
  played instead.
- The sidebar marks every reviewed move with its rating, colour-coded from green
  (best) to red (blunder).

Click any move in the sidebar, or use **←**/**→**, to step through the game and see the
position at that point. **Space** plays the game back automatically.

---

## Clocks

Choose **Off**, **Stopwatch** or **Blitz** in Options.

- **Stopwatch** counts up for each side; purely informational.
- **Blitz 5+3** and **Blitz 10+0** count down. Running out of time ends the game and the
  opponent wins on time.

Clock times are shown in the status bar and turn amber below 20 seconds.

---

## Saving, loading and resuming

- **S** (or **Ctrl+S**) saves to the data directory as `saved_game.json`.
- **L** (or **Ctrl+O**) loads it, rebuilding the position from the recorded moves and
  validating each one.
- The game **autosaves** every ten moves, when a game ends, and when you quit.
- If an autosave exists at start-up you are offered **Resume** or **Start fresh**.

Save files are versioned and portable between operating systems. Iago 3.0 save files
still load.

---

## Keyboard reference

Press **F1** in game for this list.

| Key | Action |
|---|---|
| Click | Play / inspect |
| N, R | New game |
| U, Ctrl+Z | Undo |
| Y, Ctrl+Y | Redo |
| H | Toggle hints |
| Space | Engine hint *(replay: play/pause)* |
| D, 1–5 | Difficulty |
| M | Game mode |
| T | Theme |
| B | Board size |
| V | Mute |
| S, Ctrl+S | Save |
| L, Ctrl+O | Load |
| A | Analyse |
| P | Pause AI vs AI |
| + / − | AI vs AI speed |
| ← / → / Home / End | Replay stepping |
| O, Tab | Options |
| F1 | Controls |
| F11 | Fullscreen |
| F3 | Debug overlay |
| Esc | Close overlay / quit |

---

## Command line

```
iago [--theme KEY] [--mode {hvai,hvh,ava}] [--level 1..5] [--size {6,8,10}]
     [--fullscreen | --windowed] [--scale FACTOR] [--sound | --no-sound]
     [--data-dir PATH] [--reset-settings] [--verbose | --quiet]
     [--list-themes] [--list-controls] [--version]
```

Examples:

```bash
iago --list-themes
iago --theme midnight --level 5
iago --mode ava --level 4 --size 10
iago --no-sound --data-dir ./profile
```

---

## Troubleshooting

**The window does not open.**
Check the log written to the data directory (see `iago --verbose`). On a headless
machine set `SDL_VIDEODRIVER=dummy` — the game runs but draws nowhere.

**No sound.**
Some minimal systems have no audio device; the game detects this and runs silently. Use
**Options → Audio → Play test** to check.

**Text is missing or the game looks wrong.**
Iago needs `pygame-ce` 2.5.4 or newer. With plain `pygame` 2.6.1 on Python 3.14 the font
module fails to import — reinstall with `pip install --force-reinstall pygame-ce`.

**Everything is too small.**
Use **Options → Appearance → Interface scale**, or start with `--scale 1.25`.

**I want a clean slate.**
Delete the data directory (see the README), or start with `--reset-settings`.

**A save file will not load.**
The loader rejects any file whose moves are illegal; the error toast names the offending
move. The file format is documented in [SAVE_FORMAT.md](SAVE_FORMAT.md).
