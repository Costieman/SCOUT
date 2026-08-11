from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.run_tiingo_sp500_durable_slice import _load_target_symbols

CURRENT_REVIEWED = {
    "A",
    "ABNB",
    "AIZ",
    "AKAM",
    "ALLE",
    "AMP",
    "AMZN",
    "ANET",
    "APP",
    "APTV",
    "AWK",
    "AXON",
}


def test_checked_in_research_50_scope_is_bounded_and_retains_current_reviewed() -> None:
    path = Path("configs/tiingo_research_50_targets_v0.1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot_symbols = (*payload["symbols"], "ZZZ")

    target = _load_target_symbols(path, "tiingo-sp500-2026-08-10-v0.1", snapshot_symbols)

    assert len(target) == 50
    assert CURRENT_REVIEWED.issubset(target)
    assert "ZZZ" not in target


def test_target_scope_rejects_symbol_outside_validated_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    payload = {
        "schema_version": "tiingo-research-targets-v0.1",
        "target_version": "test-v1",
        "source_universe_plan": "plan-v1",
        "purpose": "test",
        "target_count": 2,
        "symbols": ["AAA", "OUTSIDE"],
        "selection_notes": ["test"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="outside the validated snapshot"):
        _load_target_symbols(path, "plan-v1", ("AAA", "BBB"))


def test_target_scope_rejects_wrong_universe_plan(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    payload = {
        "schema_version": "tiingo-research-targets-v0.1",
        "target_version": "test-v1",
        "source_universe_plan": "other-plan",
        "purpose": "test",
        "target_count": 1,
        "symbols": ["AAA"],
        "selection_notes": ["test"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="another Tiingo universe plan"):
        _load_target_symbols(path, "plan-v1", ("AAA",))
