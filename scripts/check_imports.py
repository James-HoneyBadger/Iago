#!/usr/bin/env python3
"""Print the project's internal import graph and flag layering violations.

The documented rule is ``app → ui → ai → core`` with ``util`` underneath
everything.  Run this after adding imports::

    python scripts/check_imports.py          # summary + violations
    python scripts/check_imports.py --full   # every cross-layer edge

Exit code is 1 when a violation is found, so it can gate a commit.
"""

from __future__ import annotations

import argparse
import ast
import collections
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "iago"
PACKAGE_NAME = "iago"

#: Higher numbers may import lower numbers; anything else is a violation.
LAYERS = {"core": 0, "ai": 1, "ui": 2, "app": 3}
#: Layers that everything may import.
SHARED = {"util", "branding"}

#: Deliberate upward imports: ``ui`` renders value objects owned by ``app``.
#: The point of the rule is that ``ui`` must never reach the controller
#: (``app.game``) or the CLI, which would create a cycle.
ALLOWED_UPWARD = {
    ("ui", "app"): {
        "session",
        "settings",
        "analysis",
        "achievements",
        "keymap",
    },
}


def module_name(path: Path) -> str:
    """Package-relative module name (``app/game.py`` → ``app.game``)."""

    parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def resolve(node: ast.ImportFrom, path: Path) -> str:
    """Absolute module name for a relative import (``from ..core import x``)."""

    if not node.level:
        return node.module or ""
    package = list(path.relative_to(PACKAGE).with_suffix("").parts)[:-1]
    drop = node.level - 1
    if drop:
        package = package[:-drop] if drop <= len(package) else []
    parts = package + (node.module.split(".") if node.module else [])
    return ".".join([PACKAGE_NAME, *parts])


def imports_of(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = resolve(node, path)
            if target == PACKAGE_NAME:
                found.add("__root__")
            elif target.startswith(PACKAGE_NAME + "."):
                found.add(target[len(PACKAGE_NAME) + 1 :])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE_NAME + "."):
                    found.add(alias.name[len(PACKAGE_NAME) + 1 :])
    return {name for name in found if name}


def layer_of(module: str) -> str:
    """Layer of a package-relative module name (``app.game`` → ``app``)."""

    return module.split(".")[0]


def is_violation(source: str, target: str) -> bool:
    """True when *target* may not be imported from *source*.

    A dependency is a violation when it points *up* a layer and is not one of
    the documented value-object exceptions.
    """

    source_layer, target_layer = layer_of(source), layer_of(target)
    if source_layer not in LAYERS or target_layer not in LAYERS:
        return False
    if LAYERS[target_layer] <= LAYERS[source_layer]:
        return False
    allowed = ALLOWED_UPWARD.get((source_layer, target_layer), set())
    return target.split(".")[1] not in allowed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="list every edge")
    args = parser.parse_args(argv)

    edges: Dict[Tuple[str, str], List[str]] = collections.defaultdict(list)
    for path in sorted(PACKAGE.rglob("*.py")):
        source = module_name(path)
        for target in imports_of(path):
            source_layer = layer_of(source)
            target_layer = layer_of(target)
            if source_layer == target_layer or target_layer in SHARED:
                continue
            edges[(source_layer, target_layer)].append(f"{source} → {target}")

    violations: List[str] = []
    for (source_layer, target_layer), items in sorted(edges.items()):
        if source_layer in LAYERS and target_layer in LAYERS:
            upward = LAYERS[target_layer] > LAYERS[source_layer]
            bad = [item for item in items if is_violation(*item.split(" → "))]
            if upward and bad:
                verdict = "VIOLATION"
                violations.extend(bad)
            elif upward:
                verdict = "allowed"
            else:
                verdict = "ok"
        else:
            verdict = "ok"
        print(f"{source_layer:5s} → {target_layer:5s}  {verdict:9s} ({len(items)})")
        if args.full:
            for item in sorted(items):
                print(f"    {item}")

    if violations:
        print("\nLayering violations:", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        return 1
    print("\nNo layering violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
