"""The documented layering rules, enforced.

`scripts/check_imports.py` is the single implementation; this test drives it so the
architecture cannot rot silently.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_imports.py"


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("iago_check_imports", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_real_tree_has_no_layering_violations(checker, capsys):
    assert checker.main([]) == 0
    assert "No layering violations" in capsys.readouterr().out


def test_layers_point_downwards(checker):
    assert not checker.is_violation("app.game", "ui.renderer")
    assert not checker.is_violation("app.game", "core.board")
    assert not checker.is_violation("ui.renderer", "ai.search")
    assert not checker.is_violation("ai.search", "core.bitboard")
    assert not checker.is_violation("core.board", "util.errors")


def test_upward_imports_are_violations(checker):
    assert checker.is_violation("core.bitboard", "ai.search")
    assert checker.is_violation("ai.engine", "ui.theme")
    assert checker.is_violation("ui.renderer", "app.game")


def test_ui_may_import_app_value_objects_only(checker):
    for module in ("session", "settings", "analysis", "achievements", "keymap"):
        assert not checker.is_violation("ui.overlays", f"app.{module}")
    # ... but never the controller or the CLI.
    assert checker.is_violation("ui.overlays", "app.game")
    assert checker.is_violation("ui.overlays", "app.paths")
