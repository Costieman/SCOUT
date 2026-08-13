"""Tests for the one-command private Experiment A pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from scripts.run_experiment_a_pipeline import (
    _benchmark_promotion_command,
    _composition_command,
    _default_target_version,
    _experiment_command,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.experiments.benchmark_config import load_experiment_a_benchmark_config


def _benchmark():
    path = Path(__file__).resolve().parents[2] / "configs" / "experiment_a_spy_benchmark_v0.1.json"
    return load_experiment_a_benchmark_config(path)


def test_target_version_is_deterministic_from_immutable_sources() -> None:
    value = _default_target_version(
        DatasetVersion("research-v1"),
        DatasetVersion("benchmark-v1"),
    )
    assert value == "research-v1__with__benchmark-v1"


def test_pipeline_commands_preserve_explicit_source_versions_and_benchmark_identity() -> None:
    repository = Path("/repo")
    root = Path("/private/workspace")
    benchmark = _benchmark()
    research = DatasetVersion("research-v1")
    target = DatasetVersion("research-v1__with__tiingo-spy-split-only-v0.1")

    promote = _benchmark_promotion_command(
        repository,
        root,
        repository / "configs" / "experiment_a_spy_benchmark_v0.1.json",
    )
    compose = _composition_command(repository, root, research, benchmark, target)
    execute = _experiment_command(
        repository,
        root,
        target,
        benchmark,
        sampling_stride=5,
        sma_slope_lookback=20,
        trailing_return_intervals=60,
        relative_strength_intervals=60,
    )

    assert "promote_experiment_a_benchmark.py" in promote[1]
    assert str(benchmark.definition.dataset_version) in compose
    assert str(research) in compose
    assert str(target) in compose
    assert "run_experiment_a.py" in execute[1]
    assert str(benchmark.definition.instrument_id) in execute
    assert str(target) in execute
