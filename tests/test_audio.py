"""Tests for the synthesised sound effects."""

from __future__ import annotations

import array

import pygame as pg
import pytest

from iago.app.audio import CHANNELS, SAMPLE_RATE, SoundBank, synthesize


def test_synthesize_produces_stereo_samples():
    samples = synthesize([(440.0, 0.1)])
    assert isinstance(samples, array.array)
    assert len(samples) == int(SAMPLE_RATE * 0.1) * CHANNELS
    assert max(abs(value) for value in samples) > 0
    assert all(-32768 <= value <= 32767 for value in samples)


def test_synthesize_silence():
    samples = synthesize([(0.0, 0.05)], wave="sine")
    assert all(value == 0 for value in samples)


def test_synthesize_sequences_are_concatenated():
    one = synthesize([(300.0, 0.02)])
    two = synthesize([(300.0, 0.02), (300.0, 0.02)])
    assert len(two) == len(one) * 2


@pytest.mark.parametrize("wave", ["sine", "triangle", "square", "noise"])
def test_waveforms_are_bounded(wave):
    samples = synthesize([(220.0, 0.02)], wave=wave, amplitude=0.5)
    assert samples
    assert max(abs(value) for value in samples) <= 32767


def test_sound_bank_initialises_with_dummy_driver():
    bank = SoundBank(enabled=True, volume=0.5)
    assert bank.available
    assert {"place", "flip", "invalid", "win", "lose", "draw"} <= set(bank.sounds)


def test_place_sound_is_the_right_length():
    bank = SoundBank()
    raw = bank.sounds["place"].get_raw()
    # 16-bit stereo: two bytes per channel per frame.
    frames = len(raw) / (2 * CHANNELS)
    assert frames / SAMPLE_RATE > 0.05


def test_play_is_safe_when_muted():
    bank = SoundBank(enabled=False)
    bank.play("place")
    bank.set_enabled(True)
    bank.set_volume(0.1)
    bank.play("flip", variant=3)
    bank.set_volume(5.0)
    assert bank.volume == pytest.approx(1.0)
    bank.shutdown()


def test_sound_bank_survives_a_broken_mixer(monkeypatch):
    def boom(*args, **kwargs):
        raise pg.error("no audio")

    monkeypatch.setattr(pg.mixer, "init", boom)
    monkeypatch.setattr(pg.mixer, "get_init", lambda: None)
    bank = SoundBank()
    assert not bank.available
    bank.play("place")  # must not raise
