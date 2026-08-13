"""Governed batch construction and comparison for Experiment A trend contexts.

This module materializes the complete T0-T6 search space before execution and provides a compact,
descriptive comparison table after all child runs finish. It does not select a winning trend context
or make inferential or production claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trade_scout.experiments.contracts import ExperimentDefinition, JSONValue
from trade_scout.experiments.planner import ExperimentBatchPlan, plan_experiment_batch
from trade_scout.experiments.trend_baseline import experiment_a_definition
from trade_scout.features.trend_context import TrendContext


@dataclass(frozen=True, slots=True)
class ExperimentABatchConfig:
    """Fully resolved shared configuration for the seven Experiment A child runs."""

    dataset_version: str
    universe_version: str
    code_version: str
    config_schema_version: str
    outcome_horizons: tuple[int, ...] = (5, 10, 20, 40, 60, 120, 252)
    sampling_stride: int = 5
    sma_slope_lookback: int = 20
    trailing_return_intervals: int = 60
    relative_strength_intervals: int = 60


@dataclass(frozen=True, slots=True)
class ExperimentAComparisonRow:
    """One trend-context/horizon descriptive comparison row."""

    trend_context: TrendContext
    horizon: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    median_mfe: float | None
    median_mae: float | None
    median_max_drawdown: float | None


class StageOutputReader(Protocol):
    """Minimum persisted-output interface required to compare Experiment A child runs."""

    def read_stage_output(self, experiment_id: str, stage_name: str) -> dict[str, JSONValue]: ...


def experiment_a_definitions(config: ExperimentABatchConfig) -> tuple[ExperimentDefinition, ...]:
    """Materialize the canonical ordered T0-T6 Experiment A child definitions."""

    return tuple(
        experiment_a_definition(
            trend_context=context,
            dataset_version=config.dataset_version,
            universe_version=config.universe_version,
            code_version=config.code_version,
            config_schema_version=config.config_schema_version,
            outcome_horizons=config.outcome_horizons,
            sampling_stride=config.sampling_stride,
            sma_slope_lookback=config.sma_slope_lookback,
            trailing_return_intervals=config.trailing_return_intervals,
            relative_strength_intervals=config.relative_strength_intervals,
        )
        for context in TrendContext
    )


def plan_experiment_a_batch(config: ExperimentABatchConfig) -> ExperimentBatchPlan:
    """Create one immutable governed T0-T6 plan before any Experiment A child executes."""

    parent = experiment_a_definition(
        trend_context=TrendContext.T0,
        dataset_version=config.dataset_version,
        universe_version=config.universe_version,
        code_version=config.code_version,
        config_schema_version=config.config_schema_version,
        outcome_horizons=config.outcome_horizons,
        sampling_stride=config.sampling_stride,
        sma_slope_lookback=config.sma_slope_lookback,
        trailing_return_intervals=config.trailing_return_intervals,
        relative_strength_intervals=config.relative_strength_intervals,
    )
    return plan_experiment_batch(
        parent,
        {"experiment_a.trend_context": tuple(context.value for context in TrendContext)},
    )


def compare_experiment_a_outputs(
    experiment_ids_by_context: dict[TrendContext, str],
    reader: StageOutputReader,
) -> tuple[ExperimentAComparisonRow, ...]:
    """Read persisted child outputs and return deterministic descriptive comparison rows."""

    expected = set(TrendContext)
    observed = set(experiment_ids_by_context)
    if observed != expected:
        missing = ", ".join(sorted(item.value for item in expected - observed))
        extra = ", ".join(sorted(item.value for item in observed - expected))
        raise ValueError(
            f"Experiment A comparison requires exactly T0-T6; missing={missing}; extra={extra}"
        )

    rows: list[ExperimentAComparisonRow] = []
    for context in TrendContext:
        experiment_id = experiment_ids_by_context[context]
        output = reader.read_stage_output(experiment_id, "trend_baseline")
        if output.get("program_experiment") != "A":
            raise ValueError(f"experiment {experiment_id} is not an Experiment A run")
        if output.get("trend_context") != context.value:
            raise ValueError(
                f"experiment {experiment_id} does not match trend context {context.value}"
            )
        summaries = output.get("summaries")
        if not isinstance(summaries, list):
            raise ValueError("Experiment A stage output is missing summary rows")
        for summary in summaries:
            if not isinstance(summary, dict):
                raise ValueError("Experiment A summary rows must be mappings")
            rows.append(
                ExperimentAComparisonRow(
                    trend_context=context,
                    horizon=_required_int(summary, "horizon"),
                    sample_size=_required_int(summary, "sample_size"),
                    mean_return=_optional_float(summary, "mean_return"),
                    median_return=_optional_float(summary, "median_return"),
                    positive_fraction=_optional_float(summary, "positive_fraction"),
                    median_mfe=_optional_float(summary, "median_mfe"),
                    median_mae=_optional_float(summary, "median_mae"),
                    median_max_drawdown=_optional_float(summary, "median_max_drawdown"),
                )
            )
    return tuple(sorted(rows, key=lambda item: (item.horizon, item.trend_context.value)))


def _required_int(values: dict[str, JSONValue], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Experiment A summary field {key} must be an integer")
    return value


def _optional_float(values: dict[str, JSONValue], key: str) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Experiment A summary field {key} must be numeric or null")
    return float(value)
