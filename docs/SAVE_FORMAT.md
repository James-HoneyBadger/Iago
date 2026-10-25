# Save format

Everything Iago writes is JSON, versioned, validated and written atomically. Files live
in the platform data directory (see the README); override with `--data-dir` or
`IAGO_DATA_DIR`.

- [Files](#files)
- [settings.json (schema 2)](#settingsjson-schema-2)
- [stats.json (schema 2)](#statsjson-schema-2)
- [Saved games (schema 4)](#saved-games-schema-4)
- [Migration table](#migration-table)
- [Guarantees](#guarantees)

---

## Files

| File | Purpose | Written when |
|---|---|---|
| `settings.json` | preferences | any option change, and on quit (window size included) |
| `stats.json` | statistics and achievements | end of a Human-vs-AI game, quit |
| `saved_game.json` | manual save | **S** / **Ctrl+S** |
| `autosave.json` | crash-safe resume point | every 10 moves, game over, quit |
| `iago.log` | rotating log (512 KB × 3) | continuously |

---

## settings.json (schema 2)

```json
{
  "schema": 2,
  "app_version": "4.0.0",
  "settings": {
    "theme": "classic",
    "sound_enabled": true,
    "sound_volume": 0.6,
    "show_hints": true,
    "animations": true,
    "particles": true,
    "show_coordinates": true,
    "show_eval_bar": true,
    "ai_level": 3,
    "mode": "hvai",
    "player_color": 1,
    "board_size": 8,
    "clock_mode": "off",
    "blitz_minutes": 5,
    "blitz_increment": 3,
    "fullscreen": false,
    "ui_scale": 1.0,
    "window_width": 1100,
    "window_height": 800
  }
}
```

| Field | Type | Range / values |
|---|---|---|
| `theme` | string | `classic`, `wood`, `ocean`, `sunset`, `forest`, `midnight`, `contrast` |
| `mode` | string | `hvai`, `hvh`, `ava` |
| `player_color` | int | `1` black, `2` white |
| `board_size` | int | `6`, `8`, `10` |
| `ai_level` | int | `1`–`5` |
| `clock_mode` | string | `off`, `stopwatch`, `blitz` |
| `sound_volume`, `ui_scale` | float | clamped to their allowed ranges |
| `window_*` | int | clamped to `760×660` … `2400×1800` |

Anything out of range is clamped and unknown keys are ignored, so a hand-edited file can
never put the game into an invalid state.

---

## stats.json (schema 2)

```json
{
  "schema": 2,
  "app_version": "4.0.0",
  "stats": {
    "games_played": 42,
    "games_won": 24,
    "games_lost": 14,
    "games_drawn": 4,
    "total_moves": 2394,
    "best_score": 52,
    "win_streak": 6,
    "loss_streak": 3,
    "current_streak": 2,
    "fastest_win_moves": 38,
    "longest_game_moves": 60,
    "total_time": 8123.5,
    "by_level": {
      "1": {"played": 4, "won": 4, "lost": 0, "drawn": 0, "best_score": 64},
      "2": {"played": 8, "won": 6, "lost": 2, "drawn": 0, "best_score": 56}
    },
    "achievements": ["first_win", "ten_wins", "beat_master"]
  }
}
```

`current_streak` is positive for a win streak and negative for a loss streak.
`by_level` keys are difficulty numbers as strings (JSON object keys are always strings;
they are parsed back to `int`).

---

## Saved games (schema 4)

```json
{
  "schema": 4,
  "app_version": "4.0.0",
  "saved_at": "2025-10-25T14:03:11+00:00",
  "board_size": 8,
  "mode": "hvai",
  "ai_level": 4,
  "player_color": 1,
  "moves": [
    {"player": 1, "row": 2, "col": 3},
    {"player": 2, "row": 2, "col": 4}
  ],
  "result": {"game_over": false, "winner": null},
  "clocks": {"mode": "blitz", "elapsed": {"1": 12.4, "2": 9.8}}
}
```

Only the **move list** is authoritative. Loading replays it against `Board` and rejects
the file if any move is illegal for the side to move — so a save can never describe an
impossible position, and the format stays compact and diff-friendly.

`result` is informational (used for the resume prompt); `clocks.elapsed` is restored as
the starting elapsed time for each side.

---

## Migration table

| File | Old | New | What happens |
|---|---|---|---|
| `settings.json` | v1 flat | v2 | `ai_difficulty` name (`"EXPERT"`) mapped to a level number; unknown keys dropped; new fields defaulted |
| `stats.json` | v1 flat | v2 | flat counters kept, per-level table and achievements initialised |
| `saved_game.json` | v3 (`board_grid`, `move_log`, `settings`) | v4 | `move_log` converted to `moves`, settings hoisted to top level, grid rebuilt from the moves |
| `autosave.json` | v3 | v4 | same as above, then the resume prompt is offered |

Legacy files written by Iago 3.0 in the source directory are found automatically the
first time the game runs and migrated into the data directory.

---

## Guarantees

**Atomic writes.** `atomic_write_json` writes to a temporary file in the same directory,
calls `fsync`, then `os.replace`. A crash leaves either the old file or the new one —
never a half-written file.

**Validation on read.** Missing files, invalid JSON, non-object payloads, out-of-range
values and illegal moves all produce a typed error (`SaveFileError`, `SettingsError`) or a
documented fallback to defaults. Nothing raises a bare exception to the user, and nothing
silently drops data that could be recovered.

**Forward compatibility.** Readers check `schema` and dispatch to the right parser. A file
with a schema newer than the running build is reported as unsupported rather than
misinterpreted.
