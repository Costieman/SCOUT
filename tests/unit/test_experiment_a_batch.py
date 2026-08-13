"""Tests for governed Experiment A T0-T6 planning and comparison."""

from __future__ import annotations

from trade_scout.experiments.trend_baseline_batch import (
    ExperimentABatchConfig,
    compare_experiment_a_outputs,
    plan_experiment_a_batch,
)
from trade_scout.features.trend_context import TrendContext


class _Reader:
    def read_stage_output(self, experiment_id: str, stage_name: str):
        context = experiment_id.rsplit("_", maxsplit=1)[-1]
        return {
            "program_experiment": "A",
            "trend_context": context,
            "summaries": [
                {
                    "horizon": 20,
                    "sample_size": 10,
                    "mean_return": 0.05,
                    "median_return": 0.04,
                    "positive_fraction": 0.7,
                    "median_mfe": 0.08,
                    "median_mae": -0.03,
                    "median_max_drawdown": -0.04,
                }
            ],
        }


def _config() -> ExperimentABatchConfig:
    return ExperimentABatchConfig(
        dataset_version="dataset-v1",
        universe_version="universe-v1",
        code_version="code-v1",
        config_schema_version="0.1.0",
    )


def test_plan_materializes_exact_canonical_t0_t6_search_space() -> None:
    plan = plan_experiment_a_batch(_config())

    assert plan.run_count == 7
    assert plan.parameter_grid["experiment_a.trend_context"] == tuple(
        context.value for context in TrendContext
    )
    observed = tuple(
        child.definition.resolved_configuration["experiment_a"]["trend_context"]
        for child in plan.children
    )
    assert observed == tuple(context.value for context in TrendContext)
    assert all(child.definition.mode.value == "EXPLORATORY" for child in plan.children)


def test_comparison_requires_and_orders_all_seven_contexts() -> None:
    ids = {context: f"experiment_{context.value}" for context in TrendContext}

    rows = compare_experiment_a_outputs(ids, _Reader())

    assert len(rows) == 7
    assert tuple(row.trend_context for row in rows) == tuple(TrendContext)
    assert all(row.horizon == 20 for row in rows)
    assert all(row.sample_size == 10 for row in rows)


def test_comparison_rejects_incomplete_context_set() -> None:
    ids = {context: f"experiment_{context.value}" for context in TrendContext if context is not TrendContext.T6}

    try:
        compare_experiment_a_outputs(ids, _Reader())
    except ValueError as error:
        assert "missing=T6" in str(error)
    else:
        raise AssertionError("incomplete T0-T6 comparison should fail")
