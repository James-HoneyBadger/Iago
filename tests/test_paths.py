"""Tests for the platform data-directory resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from iago.app import paths
from iago.branding import APP_SLUG, DATA_DIR_NAME


@pytest.fixture(autouse=True)
def _clear_override(monkeypatch):
    monkeypatch.delenv(paths.ENV_OVERRIDE, raising=False)


def test_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_OVERRIDE, str(tmp_path / "profile"))
    assert paths.data_dir() == tmp_path / "profile" / DATA_DIR_NAME


def test_override_expands_the_user_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(paths.ENV_OVERRIDE, "~/nested/profile")
    assert paths.data_dir() == tmp_path / "nested" / "profile" / DATA_DIR_NAME


def test_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.data_dir() == tmp_path / "roaming" / DATA_DIR_NAME


def test_windows_falls_back_to_the_home_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.data_dir() == tmp_path / "AppData" / "Roaming" / DATA_DIR_NAME


def test_macos_uses_application_support(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    expected = tmp_path / "Library" / "Application Support" / DATA_DIR_NAME
    assert paths.data_dir() == expected


def test_linux_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.data_dir() == tmp_path / "xdg" / DATA_DIR_NAME


def test_linux_defaults_to_local_share(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.data_dir() == tmp_path / ".local" / "share" / DATA_DIR_NAME


def test_data_dir_is_created(monkeypatch, tmp_path):
    target = tmp_path / "fresh"
    monkeypatch.setenv(paths.ENV_OVERRIDE, str(target))
    data = paths.data_dir()
    assert data.is_dir()


def test_named_paths_live_in_the_data_dir(data_dir):
    assert paths.settings_path().parent == data_dir
    assert paths.stats_path().name == "stats.json"
    assert paths.autosave_path().name == "autosave.json"
    assert paths.log_path().name == f"{APP_SLUG}.log"


@pytest.mark.parametrize(
    "name, expected",
    [("save", "save.json"), ("my game!", "mygame.json"), ("!!!", "saved_game.json")],
)
def test_save_path_sanitises_names(data_dir, name, expected):
    assert paths.save_path(name).name == expected


def test_legacy_candidates_find_files_in_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "legacy.json").write_text("{}", encoding="utf-8")
    found = paths.legacy_candidates("legacy.json")
    assert Path(tmp_path / "legacy.json") in found
    assert paths.legacy_candidates("missing.json") == []


def test_find_existing_returns_the_first_hit(tmp_path):
    present = tmp_path / "a.json"
    present.write_text("{}", encoding="utf-8")
    assert paths.find_existing(None, tmp_path / "missing.json", present) == present
    assert paths.find_existing(None, tmp_path / "missing.json") is None
