"""Tests for the command-line entry point."""

from __future__ import annotations

import os

import pygame as pg
import pytest

from iago import cli
from iago.app import paths
from iago.branding import DATA_DIR_NAME
from iago.branding import APP_NAME


@pytest.fixture()
def captured(monkeypatch, data_dir):
    """Silence the display and capture what ``main`` launches."""

    created: list = []
    monkeypatch.setattr(cli.Game, "run", lambda self: created.append(self))
    return created


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert APP_NAME in capsys.readouterr().out


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.theme is None
    assert args.mode is None
    assert args.level is None
    assert args.size is None
    assert args.seed is None
    assert args.sound is None
    assert args.fullscreen is False


def test_parser_rejects_unknown_theme():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--theme", "nope"])


def test_list_themes_prints_every_theme(capsys, data_dir):
    assert cli.main(["--list-themes"]) == 0
    out = capsys.readouterr().out
    for key in ("classic", "midnight"):
        assert key in out


def test_list_controls_prints_bindings(capsys, data_dir):
    assert cli.main(["--list-controls"]) == 0
    out = capsys.readouterr().out
    assert "Mouse" in out
    assert out.count(":") > 2


def test_data_dir_override_sets_the_environment(monkeypatch, tmp_path, captured):
    monkeypatch.delenv(paths.ENV_OVERRIDE, raising=False)
    target = tmp_path / "profile"
    assert cli.main(["--data-dir", str(target)]) == 0
    assert paths.ENV_OVERRIDE in os.environ
    assert paths.data_dir() == target / DATA_DIR_NAME
    assert captured, "the game should have been started"


def test_options_are_forwarded_to_the_game(captured):
    assert cli.main(["--theme", "midnight", "--level", "3", "--seed", "11"]) == 0
    game = captured[-1]
    assert game.theme.key == "midnight"
    assert game.settings.ai_level == 3
    assert game.options.seed == 11


def test_verbose_logging_mentions_the_log_file(capsys, data_dir, captured):
    assert cli.main(["--verbose"]) == 0
    assert "logging to" in capsys.readouterr().err


def test_display_failure_returns_two(monkeypatch, data_dir):
    def boom(self, options):
        raise pg.error("no display")

    monkeypatch.setattr(cli.Game, "__init__", boom)
    assert cli.main([]) == 2


def test_iago_error_returns_two(monkeypatch, data_dir):
    from iago.util.errors import IagoError

    def boom(self, options):
        raise IagoError("bad board")

    monkeypatch.setattr(cli.Game, "__init__", boom)
    assert cli.main([]) == 2


def test_keyboard_interrupt_shuts_down(monkeypatch, data_dir, captured):
    stopped: list = []
    monkeypatch.setattr(
        cli.Game, "run", lambda self: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    monkeypatch.setattr(cli.Game, "shutdown", lambda self: stopped.append(True))
    assert cli.main([]) == 0
    assert stopped
