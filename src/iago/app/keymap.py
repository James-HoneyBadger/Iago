"""Keyboard bindings.

A single table drives three things: the controller's dispatch, the help overlay
and the controls tab in the options, so they can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pygame as pg

GLOBAL = "Global"
PLAYING = "Playing"
REPLAY = "Replay"
AI_VS_AI = "AI vs AI"


@dataclass(frozen=True)
class Binding:
    keys: Tuple[int, ...]
    action: str
    label: str
    display: str
    context: str = GLOBAL
    modifiers: int = 0

    def matches(self, key: int, mods: int) -> bool:
        if key not in self.keys:
            return False
        relevant = mods & (pg.KMOD_CTRL | pg.KMOD_ALT | pg.KMOD_META | pg.KMOD_SHIFT)
        if self.modifiers:
            if (relevant & self.modifiers) != self.modifiers:
                return False
            extra = (
                relevant & ~self.modifiers & (pg.KMOD_CTRL | pg.KMOD_ALT | pg.KMOD_META)
            )
            return not extra
        return not (relevant & (pg.KMOD_CTRL | pg.KMOD_ALT | pg.KMOD_META))


BINDINGS: Sequence[Binding] = (
    # Global
    Binding((pg.K_F1,), "help", "Help / shortcuts", "F1"),
    Binding((pg.K_o, pg.K_TAB), "options", "Options", "O / Tab"),
    Binding((pg.K_F11,), "fullscreen", "Toggle fullscreen", "F11"),
    Binding((pg.K_F3,), "debug", "Toggle debug overlay", "F3"),
    Binding((pg.K_ESCAPE,), "escape", "Close overlay / quit", "Esc"),
    Binding((pg.K_s,), "save", "Save game", "S", modifiers=pg.KMOD_CTRL),
    Binding((pg.K_o,), "load", "Load game", "Ctrl+O", modifiers=pg.KMOD_CTRL),
    # Playing
    Binding((pg.K_n, pg.K_r), "new_game", "New game", "N / R", PLAYING),
    Binding((pg.K_u,), "undo", "Undo", "U", PLAYING),
    Binding((pg.K_y,), "redo", "Redo", "Y", PLAYING),
    Binding((pg.K_z,), "undo", "Undo", "Ctrl+Z", PLAYING, pg.KMOD_CTRL),
    Binding((pg.K_y,), "redo", "Redo", "Ctrl+Y", PLAYING, pg.KMOD_CTRL),
    Binding(
        (pg.K_z,), "redo", "Redo", "Ctrl+Shift+Z", PLAYING, pg.KMOD_CTRL | pg.KMOD_SHIFT
    ),
    Binding((pg.K_h,), "toggle_hints", "Show / hide hints", "H", PLAYING),
    Binding((pg.K_SPACE,), "hint", "Ask the engine for a hint", "Space", PLAYING),
    Binding((pg.K_d,), "cycle_level", "Cycle difficulty", "D", PLAYING),
    Binding((pg.K_m,), "cycle_mode", "Cycle game mode", "M", PLAYING),
    Binding((pg.K_t,), "cycle_theme", "Cycle theme", "T", PLAYING),
    Binding((pg.K_b,), "cycle_board_size", "Cycle board size", "B", PLAYING),
    Binding((pg.K_v,), "toggle_sound", "Mute / unmute", "V", PLAYING),
    Binding((pg.K_s,), "save", "Save game", "S", PLAYING),
    Binding((pg.K_l,), "load", "Load game", "L", PLAYING),
    Binding((pg.K_a,), "analyse", "Analyse the game", "A", PLAYING),
    Binding(
        (pg.K_1, pg.K_2, pg.K_3, pg.K_4, pg.K_5),
        "set_level",
        "Set difficulty 1–5",
        "1–5",
        PLAYING,
    ),
    Binding((pg.K_p,), "pause", "Pause AI vs AI", "P", AI_VS_AI),
    Binding((pg.K_PLUS, pg.K_EQUALS), "faster", "Speed up AI vs AI", "+", AI_VS_AI),
    Binding((pg.K_MINUS,), "slower", "Slow down AI vs AI", "-", AI_VS_AI),
    # Replay
    Binding((pg.K_SPACE,), "replay_toggle", "Play / pause replay", "Space", REPLAY),
    Binding((pg.K_RIGHT,), "replay_next", "Next move", "→", REPLAY),
    Binding((pg.K_LEFT,), "replay_prev", "Previous move", "←", REPLAY),
    Binding((pg.K_END,), "replay_end", "Jump to end", "End", REPLAY),
    Binding((pg.K_HOME,), "replay_start", "Jump to start", "Home", REPLAY),
)


def lookup(key: int, mods: int = 0, context: str = PLAYING) -> Optional[str]:
    """Return the action bound to *key* in *context* (global bindings win)."""

    ordered = [binding for binding in BINDINGS if binding.context in (GLOBAL, context)]
    # Prefer bindings with modifiers (Ctrl+S beats plain S) and context-specific ones.
    ordered.sort(
        key=lambda binding: (
            binding.context == GLOBAL,
            -bin(binding.modifiers).count("1"),
        )
    )
    for binding in ordered:
        if binding.matches(key, mods):
            return binding.action
    return None


def bindings_by_context() -> Dict[str, List[Binding]]:
    grouped: Dict[str, List[Binding]] = {}
    for binding in BINDINGS:
        grouped.setdefault(binding.context, []).append(binding)
    return grouped


__all__ = [
    "AI_VS_AI",
    "BINDINGS",
    "Binding",
    "GLOBAL",
    "PLAYING",
    "REPLAY",
    "bindings_by_context",
    "lookup",
]
