"""Easing, timelines, particles, toasts and screen shake.

All time values are seconds.  ``now`` is supplied by the caller (normally
``pygame.time.get_ticks() / 1000``) which keeps every animation deterministic and
unit-testable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import pygame as pg

from .theme import Color


def linear(t: float) -> float:
    return t


def ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    c3 = overshoot + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + overshoot * (t - 1.0) ** 2


def ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": linear,
    "quad": ease_out_quad,
    "cubic": ease_out_cubic,
    "in_out": ease_in_out_cubic,
    "back": ease_out_back,
    "bounce": ease_out_bounce,
}


def clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


@dataclass
class Timeline:
    """A single delayed animation."""

    started: float
    duration: float
    easing: Callable[[float], float] = ease_out_cubic
    delay: float = 0.0

    def progress(self, now: float) -> float:
        if self.duration <= 0:
            return 1.0
        elapsed = now - self.started - self.delay
        return self.easing(clamp01(elapsed / self.duration))

    def active(self, now: float) -> bool:
        return self.delay + self.duration > 0 and (
            now - self.started < self.delay + self.duration
        )


class AnimationManager:
    """Keyed timelines (e.g. one flip animation per board square)."""

    def __init__(self) -> None:
        self._items: Dict[object, Timeline] = {}

    def add(
        self,
        key: object,
        started: float,
        duration: float,
        easing: str = "cubic",
        delay: float = 0.0,
    ) -> None:
        self._items[key] = Timeline(
            started, duration, EASINGS.get(easing, ease_out_cubic), delay
        )

    def progress(self, key: object, now: float, default: float = 1.0) -> float:
        timeline = self._items.get(key)
        if timeline is None:
            return default
        return timeline.progress(now)

    def active(self, key: object, now: float) -> bool:
        timeline = self._items.get(key)
        return timeline is not None and timeline.active(now)

    def prune(self, now: float) -> None:
        self._items = {
            key: timeline
            for key, timeline in self._items.items()
            if timeline.active(now)
        }

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Color
    size: float
    gravity: float = 260.0
    drag: float = 0.90


class ParticleSystem:
    """Small burst particle system for flips and celebrations."""

    def __init__(self, limit: int = 700) -> None:
        self.particles: List[Particle] = []
        self.limit = limit
        self._rng = random.Random(1234)

    def emit_burst(
        self,
        x: float,
        y: float,
        color: Color,
        count: int = 10,
        speed: float = 120.0,
        life: float = 0.55,
        size: float = 2.5,
        spread: float = math.tau,
        angle: float = 0.0,
    ) -> None:
        for _ in range(count):
            if len(self.particles) >= self.limit:
                return
            theta = angle + (self._rng.random() - 0.5) * spread
            velocity = speed * (0.35 + self._rng.random() * 0.85)
            lifespan = life * (0.6 + self._rng.random() * 0.7)
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(theta) * velocity,
                    vy=math.sin(theta) * velocity,
                    life=lifespan,
                    max_life=lifespan,
                    color=color,
                    size=size * (0.6 + self._rng.random() * 0.8),
                )
            )

    def emit_confetti(
        self, rect: Tuple[int, int, int, int], colors: List[Color], count: int = 60
    ) -> None:
        x0, y0, width, _ = rect
        for _ in range(count):
            if len(self.particles) >= self.limit:
                return
            lifespan = 1.4 + self._rng.random() * 1.2
            self.particles.append(
                Particle(
                    x=x0 + self._rng.random() * width,
                    y=y0 - self._rng.random() * 40,
                    vx=(self._rng.random() - 0.5) * 80,
                    vy=self._rng.random() * 60,
                    life=lifespan,
                    max_life=lifespan,
                    color=colors[self._rng.randrange(len(colors))],
                    size=2.0 + self._rng.random() * 3.0,
                    gravity=90.0,
                    drag=0.99,
                )
            )

    def update(self, dt: float) -> None:
        alive: List[Particle] = []
        for particle in self.particles:
            particle.life -= dt
            if particle.life <= 0:
                continue
            particle.vy += particle.gravity * dt
            particle.vx *= particle.drag
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            alive.append(particle)
        self.particles = alive

    def draw(self, surface: pg.Surface) -> None:
        for particle in self.particles:
            alpha = int(255 * clamp01(particle.life / particle.max_life))
            radius = max(1, int(particle.size))
            dot = pg.Surface((radius * 2 + 2, radius * 2 + 2), pg.SRCALPHA)
            pg.draw.circle(
                dot,
                (*particle.color, alpha),
                (radius + 1, radius + 1),
                radius,
            )
            surface.blit(dot, (int(particle.x) - radius, int(particle.y) - radius))

    @property
    def count(self) -> int:
        return len(self.particles)

    def clear(self) -> None:
        self.particles.clear()


@dataclass
class Toast:
    text: str
    color: Color
    started: float
    duration: float = 1.8

    def expired(self, now: float) -> bool:
        return now - self.started > self.duration

    def alpha(self, now: float) -> int:
        elapsed = now - self.started
        if elapsed < 0 or elapsed > self.duration:
            return 0
        fade_in = 0.14
        fade_out = 0.4
        if elapsed < fade_in:
            return int(255 * elapsed / fade_in)
        if elapsed > self.duration - fade_out:
            return int(255 * (self.duration - elapsed) / fade_out)
        return 255


class ToastStack:
    """Transient status messages shown near the top of the board."""

    def __init__(self) -> None:
        self._toasts: List[Toast] = []

    def push(self, text: str, color: Color, now: float, duration: float = 1.8) -> None:
        self._toasts = [toast for toast in self._toasts if not toast.expired(now)]
        self._toasts.append(Toast(text, color, now, duration))
        if len(self._toasts) > 3:
            self._toasts = self._toasts[-3:]

    def active(self, now: float) -> List[Toast]:
        self._toasts = [toast for toast in self._toasts if toast.alpha(now) > 0]
        return list(self._toasts)

    def clear(self) -> None:
        self._toasts.clear()


class ScreenShake:
    """Decaying positional offset used for weighty impacts."""

    def __init__(self) -> None:
        self.amplitude = 0.0
        self.started = 0.0
        self.duration = 0.0

    def trigger(
        self, now: float, amplitude: float = 4.0, duration: float = 0.22
    ) -> None:
        self.amplitude = amplitude
        self.started = now
        self.duration = duration

    def offset(self, now: float) -> Tuple[int, int]:
        if self.duration <= 0:
            return 0, 0
        elapsed = now - self.started
        if elapsed >= self.duration:
            return 0, 0
        decay = 1.0 - elapsed / self.duration
        swing = math.sin(elapsed * 58.0) * self.amplitude * decay
        return int(swing), int(swing * 0.6)


class AnimatedValue:
    """Exponential smoothing towards a target (used for score counters)."""

    def __init__(self, value: float = 0.0, rate: float = 12.0) -> None:
        self.value = float(value)
        self.target = float(value)
        self.rate = rate

    def set(self, target: float) -> None:
        self.target = float(target)

    def snap(self, value: float) -> None:
        self.target = float(value)
        self.value = float(value)

    def update(self, dt: float) -> float:
        difference = self.target - self.value
        if abs(difference) < 0.01:
            self.value = self.target
        else:
            self.value += difference * min(1.0, self.rate * dt)
        return self.value

    @property
    def rounded(self) -> int:
        return int(round(self.value))


__all__ = [
    "AnimatedValue",
    "AnimationManager",
    "EASINGS",
    "Particle",
    "ParticleSystem",
    "ScreenShake",
    "Timeline",
    "Toast",
    "ToastStack",
    "clamp01",
    "ease_in_out_cubic",
    "ease_out_back",
    "ease_out_bounce",
    "ease_out_cubic",
    "ease_out_quad",
    "linear",
]
