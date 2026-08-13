"""Tests for the checked-in Experiment A benchmark definition."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from trade_scout.experiments.benchmark_config import (
    BenchmarkConfigError,
    load_experiment_a_benchmark_config,
)


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "experiment_a_spy_benchmark_v0.1.json"


def test_checked_in_spy_benchmark_is_explicit_and_bounded() -> None:
    config = load_experiment_a_benchmark_config(_config_path())
    definition = config.definition

    assert config.benchmark_version == "experiment-a-spy-v0.1"
    assert config.provider_id == "tiingo"
    assert config.benchmark_target == "S&P 500 Index"
    assert definition.query_symbol == "SPY"
    assert definition.provider_instrument_id == "SPY"
    assert str(definition.instrument_id) == "benchmark-spy-us78462f1030"
    assert definition.exchange == "ARCX"
    assert definition.currency == "USD"
    assert definition.first_trade_date == date(1993, 1, 22)
    assert definition.dataset_start_date == date(1996, 1, 2)
    assert definition.dataset_end_date == date(2026, 8, 7)
    assert str(definition.dataset_version) == "tiingo-spy-split-only-v0.1"
    assert config.evidence_refs
    assert any("S&P 500" in note for note in config.scope_notes)


def test_benchmark_config_rejects_unknown_fields(tmp_path: Path) -> None:
    raw = json.loads(_config_path().read_text(encoding="utf-8"))
    raw["unexpected"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(BenchmarkConfigError, match="fields differ from schema"):
        load_experiment_a_benchmark_config(path)


def test_benchmark_config_rejects_unsupported_provider(tmp_path: Path) -> None:
    raw = json.loads(_config_path().read_text(encoding="utf-8"))
    raw["provider_id"] = "another-provider"
    path = tmp_path / "bad-provider.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(BenchmarkConfigError, match="supports Tiingo only"):
        load_experiment_a_benchmark_config(path)
