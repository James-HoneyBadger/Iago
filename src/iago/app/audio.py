"""Programmatic sound effects.

Everything is synthesised at start-up, so the game ships with no audio assets.
Buffers are generated as 16-bit signed stereo, matching the mixer format, which
also fixes the 8-bit-mono mismatch that made the old effects play as 25 ms
clicks instead of 100 ms tones.
"""

from __future__ import annotations

import math
import random
from array import array
from typing import Dict, List, Optional, Sequence, Tuple

import pygame as pg

from ..util.log import get_logger

logger = get_logger("app.audio")

SAMPLE_RATE = 44100
CHANNELS = 2
MAX_AMPLITUDE = 32767

Note = Tuple[float, float]  # (frequency, duration)


def _envelope(index: int, total: int, attack: float, release: float) -> float:
    position = index / max(1, total - 1)
    if position < attack:
        return position / attack
    if position > 1.0 - release:
        return max(0.0, (1.0 - position) / release)
    return 1.0


def _waveform(phase: float, kind: str) -> float:
    if kind == "sine":
        return math.sin(phase)
    if kind == "triangle":
        return (
            2.0 * abs(2.0 * (phase / math.tau - math.floor(phase / math.tau + 0.5)))
            - 1.0
        )
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0 else -1.0
    if kind == "noise":
        return random.uniform(-1.0, 1.0)
    return math.sin(phase)


def synthesize(
    notes: Sequence[Note],
    *,
    wave: str = "sine",
    amplitude: float = 0.35,
    attack: float = 0.02,
    release: float = 0.35,
    vibrato: float = 0.0,
) -> array:
    """Render a sequence of ``(frequency, duration)`` notes as stereo samples."""

    samples = array("h")
    rng = random.Random(99)
    for frequency, duration in notes:
        total = max(1, int(SAMPLE_RATE * duration))
        phase = 0.0
        for index in range(total):
            if vibrato:
                wobble = 1.0 + vibrato * math.sin(math.tau * 5.0 * index / SAMPLE_RATE)
                step = math.tau * frequency * wobble / SAMPLE_RATE
            else:
                step = math.tau * frequency / SAMPLE_RATE
            phase += step
            if wave == "noise":
                value = rng.uniform(-1.0, 1.0)
            else:
                value = _waveform(phase, wave)
            envelope = _envelope(index, total, attack, release)
            sample = int(MAX_AMPLITUDE * amplitude * value * envelope)
            sample = max(-MAX_AMPLITUDE, min(MAX_AMPLITUDE, sample))
            samples.append(sample)
            if CHANNELS == 2:
                samples.append(sample)
    return samples


def _mix(*tracks: array) -> array:
    length = max(len(track) for track in tracks)
    mixed = array("h", bytes(length * 2))
    for index in range(length):
        total = 0
        for track in tracks:
            if index < len(track):
                total += track[index]
        mixed[index] = max(-MAX_AMPLITUDE, min(MAX_AMPLITUDE, total))
    return mixed


class SoundBank:
    """Owns the mixer and every generated effect."""

    def __init__(self, enabled: bool = True, volume: float = 0.6) -> None:
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume))
        self.available = False
        self.sounds: Dict[str, pg.mixer.Sound] = {}
        self._variants: Dict[str, List[pg.mixer.Sound]] = {}
        self._initialise()

    # ------------------------------------------------------------------

    def _initialise(self) -> None:
        try:
            if pg.mixer.get_init() is None:
                pg.mixer.init(
                    frequency=SAMPLE_RATE, size=-16, channels=CHANNELS, buffer=512
                )
            self.available = True
        except (pg.error, OSError) as exc:
            logger.info("Audio unavailable (%s); running silently", exc)
            self.available = False
            return

        try:
            self.sounds = {
                "place": self._sound(
                    synthesize(
                        [(820.0, 0.055), (620.0, 0.045)],
                        wave="sine",
                        amplitude=0.45,
                        release=0.5,
                    )
                ),
                "flip": self._sound(
                    synthesize(
                        [(300.0, 0.05), (520.0, 0.05), (760.0, 0.05)],
                        wave="triangle",
                        amplitude=0.22,
                    )
                ),
                "flip_many": self._sound(
                    synthesize(
                        [(240.0, 0.05), (420.0, 0.05), (680.0, 0.05), (940.0, 0.06)],
                        wave="triangle",
                        amplitude=0.24,
                        vibrato=0.01,
                    )
                ),
                "invalid": self._sound(
                    synthesize(
                        [(160.0, 0.09), (140.0, 0.07)], wave="square", amplitude=0.14
                    )
                ),
                "pass": self._sound(
                    synthesize(
                        [(520.0, 0.08), (700.0, 0.10)], wave="sine", amplitude=0.28
                    )
                ),
                "ui": self._sound(
                    synthesize(
                        [(1180.0, 0.025)], wave="sine", amplitude=0.18, release=0.7
                    )
                ),
                "win": self._sound(
                    synthesize(
                        [
                            (523.25, 0.11),
                            (659.25, 0.11),
                            (783.99, 0.11),
                            (1046.5, 0.22),
                        ],
                        wave="triangle",
                        amplitude=0.34,
                    )
                ),
                "lose": self._sound(
                    synthesize(
                        [(440.0, 0.13), (392.0, 0.13), (329.6, 0.13), (261.6, 0.24)],
                        wave="sine",
                        amplitude=0.30,
                    )
                ),
                "draw": self._sound(
                    synthesize(
                        [(440.0, 0.10), (0.0, 0.04), (440.0, 0.12)],
                        wave="sine",
                        amplitude=0.24,
                    )
                ),
                "unlock": self._sound(
                    synthesize(
                        [(880.0, 0.07), (1174.7, 0.07), (1568.0, 0.14)],
                        wave="sine",
                        amplitude=0.30,
                    )
                ),
            }
            self._variants["flip"] = [
                self.sounds["flip"],
                self.sounds["flip"],
                self.sounds["flip_many"],
                self.sounds["flip_many"],
            ]
        except (pg.error, ValueError) as exc:  # pragma: no cover - driver specific
            logger.warning("Could not build sound effects: %s", exc)
            self.available = False
            return

        self.set_volume(self.volume)

    def _sound(self, samples: array) -> pg.mixer.Sound:
        return pg.mixer.Sound(buffer=samples.tobytes())

    # ------------------------------------------------------------------

    def play(self, name: str, variant: int = 0) -> None:
        if not (self.available and self.enabled):
            return
        sound: Optional[pg.mixer.Sound] = None
        if name == "flip" and self._variants.get("flip"):
            options = self._variants["flip"]
            sound = options[max(0, min(len(options) - 1, variant // 2))]
        else:
            sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.play()
        except (pg.error, ValueError):  # pragma: no cover - driver specific
            logger.debug("Sound %s failed to play", name)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled and pg.mixer.get_init() is not None:
            pg.mixer.stop()

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        for sound in self.sounds.values():
            try:
                sound.set_volume(self.volume)
            except (pg.error, ValueError):  # pragma: no cover
                continue

    def shutdown(self) -> None:
        if pg.mixer.get_init() is not None:
            try:
                pg.mixer.stop()
            except pg.error:  # pragma: no cover
                pass


__all__ = ["SAMPLE_RATE", "SoundBank", "synthesize"]
