"""Repository-level architecture acceptance checks.

These tests encode only accepted cross-module guardrails. They deliberately avoid inventing a
more restrictive dependency graph than the governing specifications require.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPOSITORY_ROOT / "src" / "trade_scout"
_ADR_ROOT = _REPOSITORY_ROOT / "docs" / "adr"

_REQUIRED_PACKAGE_DIRECTORIES = (
    "alerts",
    "api",
    "app",
    "common",
    "config",
    "data",
    "events",
    "experiments",
    "features",
    "outcomes",
    "patterns",
    "ranking",
    "risk",
    "scanner",
    "statistics",
    "universe",
    "validation",
)

_REQUIRED_GOVERNANCE_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "docs/README.md",
    "docs/adr/README.md",
)

# The accepted architecture requires downstream consumption, never upward coupling. Config/common
# are cross-cutting foundations and are intentionally absent from these forbidden sets. Experiments
# and validation have governed orchestration adapters in both directions, so the sweep protects
# them from production/presentation layers without pretending that relationship is a simple DAG.
_FORBIDDEN_IMPORTS: dict[str, frozenset[str]] = {
    "data": frozenset(
        {
            "events",
            "experiments",
            "features",
            "outcomes",
            "patterns",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "universe": frozenset(
        {
            "events",
            "experiments",
            "features",
            "outcomes",
            "patterns",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "features": frozenset(
        {
            "events",
            "experiments",
            "outcomes",
            "patterns",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "patterns": frozenset(
        {
            "events",
            "experiments",
            "outcomes",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "events": frozenset(
        {
            "experiments",
            "outcomes",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "outcomes": frozenset(
        {
            "experiments",
            "risk",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "risk": frozenset(
        {
            "experiments",
            "statistics",
            "validation",
            "scanner",
            "ranking",
            "alerts",
            "api",
            "app",
        }
    ),
    "statistics": frozenset({"validation", "scanner", "ranking", "alerts", "api", "app"}),
    "validation": frozenset({"scanner", "ranking", "alerts", "api", "app"}),
    "experiments": frozenset({"scanner", "ranking", "alerts", "api", "app"}),
    "scanner": frozenset({"alerts", "api", "app"}),
    "ranking": frozenset({"alerts", "api", "app"}),
}

_ADR_PATTERN = re.compile(r"^ADR-(\d{4})-[A-Za-z0-9][A-Za-z0-9-]*\.md$")


def test_repository_skeleton_matches_governing_module_map() -> None:
    missing = tuple(
        name for name in _REQUIRED_PACKAGE_DIRECTORIES if not (_PACKAGE_ROOT / name).is_dir()
    )
    assert missing == (), f"missing canonical package directories: {missing}"


def test_required_governance_files_are_present() -> None:
    missing = tuple(
        relative
        for relative in _REQUIRED_GOVERNANCE_PATHS
        if not (_REPOSITORY_ROOT / relative).is_file()
    )
    assert missing == (), f"missing repository governance files: {missing}"


def test_adr_identifiers_are_unique_and_match_headers() -> None:
    identifiers: dict[str, Path] = {}
    problems: list[str] = []
    for path in sorted(_ADR_ROOT.glob("ADR-*.md")):
        match = _ADR_PATTERN.match(path.name)
        if match is None:
            problems.append(f"invalid ADR filename: {path.name}")
            continue
        identifier = match.group(1)
        if identifier in identifiers:
            problems.append(
                f"duplicate ADR-{identifier}: {identifiers[identifier].name}, {path.name}"
            )
        identifiers[identifier] = path
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        if f"ADR-{identifier}" not in first_line:
            problems.append(f"ADR header does not match filename: {path.name}")
    assert problems == [], "\n".join(problems)


def test_protected_modules_do_not_import_forbidden_downstream_layers() -> None:
    violations: list[str] = []
    for owner, forbidden in _FORBIDDEN_IMPORTS.items():
        module_root = _PACKAGE_ROOT / owner
        for path in sorted(module_root.rglob("*.py")):
            imported_roots = _trade_scout_import_roots(path)
            for imported in sorted(imported_roots & forbidden):
                relative = path.relative_to(_REPOSITORY_ROOT)
                violations.append(f"{relative}: {owner} -> {imported}")
    assert violations == [], "forbidden Trade Scout dependency direction:\n" + "\n".join(violations)


def _trade_scout_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _absolute_trade_scout_root(alias.name)
                if root is not None:
                    roots.add(root)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "trade_scout":
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                continue
            if node.module is not None:
                root = _absolute_trade_scout_root(node.module)
                if root is not None:
                    roots.add(root)
    return roots


def _absolute_trade_scout_root(module_name: str) -> str | None:
    prefix = "trade_scout."
    if not module_name.startswith(prefix):
        return None
    remainder = module_name[len(prefix) :]
    return remainder.split(".", 1)[0]
