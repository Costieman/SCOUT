"""Persist interactive Strategy Builder research through the governed experiment stack.

The Strategy Builder remains an application client of the analytical services. This module only
adapts those services to the existing ExperimentRunner, immutable FileManifestStore, and queryable
DuckDB experiment registry so browser research is no longer ephemeral.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from trade_scout.app.strategy_builder_entry_sweep import (
    EntrySweepParameter,
    StrategyBuilderEntrySweepReport,
    StrategyBuilderEntrySweepService,
)
from trade_scout.app.strategy_builder_service import (
    StrategyBuilderError,
    StrategyBuilderReport,
    StrategyBuilderRequest,
    StrategyBuilderService,
    StrategyBuilderSource,
)
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentManifest,
    JSONValue,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.registry import DuckDBExperimentRegistry, IndexedManifestStore
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.risk.exit_policies import ManagedExitPlan, TargetFamily
from trade_scout.statistics.exit_research import ExitPolicySummary

_CAPTURE_SCHEMA = "strategy-builder-experiment-v0.2"
_STANDARD_STAGE = "strategy_builder"
_ENTRY_SWEEP_STAGE = "strategy_builder_entry_sweep"


@dataclass(frozen=True, slots=True)
class RecordedStrategyBuilderRun:
    """Successful governed Strategy Builder experiment plus its presentation report."""

    manifest: ExperimentManifest
    report: StrategyBuilderReport


@dataclass(frozen=True, slots=True)
class RecordedEntrySweepRun:
    """Successful governed entry-parameter sweep plus its presentation report."""

    manifest: ExperimentManifest
    report: StrategyBuilderEntrySweepReport


@dataclass(frozen=True, slots=True)
class StrategyBuilderExperimentRecorder:
    """Run interactive research through immutable manifests and a DuckDB metadata index."""

    experiment_root: Path
    dataset_version: str
    code_version: str
    universe_version: str = "reviewed_canonical"
    config_schema_version: str = _CAPTURE_SCHEMA

    def __post_init__(self) -> None:
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must be non-empty")
        if not self.code_version.strip():
            raise ValueError("code_version must be non-empty")
        if not self.universe_version.strip():
            raise ValueError("universe_version must be non-empty")
        if not self.config_schema_version.strip():
            raise ValueError("config_schema_version must be non-empty")

    @property
    def registry_path(self) -> Path:
        """Return the queryable local experiment-index path."""

        return self.experiment_root / "registry.duckdb"

    def run_strategy(
        self,
        source: StrategyBuilderSource,
        request: StrategyBuilderRequest,
    ) -> RecordedStrategyBuilderRun:
        """Execute and persist one ordinary Strategy Builder research request."""

        stage = _StrategyBuilderStage(
            source, request, expected_dataset_version=self.dataset_version
        )
        definition = ExperimentDefinition(
            name=f"Strategy Builder — {request.entry_family.value}",
            hypothesis="Interactive exploratory Strategy Builder hypothesis.",
            mode=ResearchMode.EXPLORATORY,
            dataset_version=self.dataset_version,
            universe_version=self.universe_version,
            code_version=self.code_version,
            config_schema_version=self.config_schema_version,
            resolved_configuration=_strategy_request_configuration(request),
        )
        try:
            manifest = self._runner().run(definition, (stage,))
        except ExperimentExecutionError as exc:
            raise StrategyBuilderError(
                f"research failed; experiment {exc.experiment_id} was saved with FAILED status"
            ) from exc
        if stage.report is None:
            raise RuntimeError("Strategy Builder experiment completed without a report")
        return RecordedStrategyBuilderRun(manifest=manifest, report=stage.report)

    def run_entry_sweep(
        self,
        source: StrategyBuilderSource,
        request: StrategyBuilderRequest,
        *,
        target_feature_name: str,
        parameter: EntrySweepParameter,
        values: tuple[float, ...],
    ) -> RecordedEntrySweepRun:
        """Execute and persist one complete declared entry-parameter response surface."""

        stage = _EntrySweepStage(
            source,
            request,
            expected_dataset_version=self.dataset_version,
            target_feature_name=target_feature_name,
            parameter=parameter,
            values=values,
        )
        configuration = _strategy_request_configuration(request)
        configuration["research_variable"] = {
            "kind": "entry_parameter_sweep",
            "target_feature_name": target_feature_name,
            "parameter": parameter.value,
            "declared_values": list(values),
            "value_count": len(values),
            "entry_populations_are_separate": True,
            "exit_policy_for_sweep": "hold_to_maximum_period_only",
        }
        definition = ExperimentDefinition(
            name=f"Strategy Builder entry sweep — {parameter.value}",
            hypothesis=(
                "Map one predeclared entry-indicator parameter while all other settings remain "
                "fixed."
            ),
            mode=ResearchMode.EXPLORATORY,
            dataset_version=self.dataset_version,
            universe_version=self.universe_version,
            code_version=self.code_version,
            config_schema_version=self.config_schema_version,
            resolved_configuration=configuration,
        )
        try:
            manifest = self._runner().run(definition, (stage,))
        except ExperimentExecutionError as exc:
            raise StrategyBuilderError(
                f"entry sweep failed; experiment {exc.experiment_id} was saved with FAILED status"
            ) from exc
        if stage.report is None:
            raise RuntimeError("entry-sweep experiment completed without a report")
        return RecordedEntrySweepRun(manifest=manifest, report=stage.report)

    def _runner(self) -> ExperimentRunner:
        registry = DuckDBExperimentRegistry(self.registry_path)
        store = IndexedManifestStore(FileManifestStore(self.experiment_root), registry)
        return ExperimentRunner(store)


class _StrategyBuilderStage:
    def __init__(
        self,
        source: StrategyBuilderSource,
        request: StrategyBuilderRequest,
        *,
        expected_dataset_version: str,
    ) -> None:
        self._source = source
        self._request = request
        self._expected_dataset_version = expected_dataset_version
        self.report: StrategyBuilderReport | None = None

    @property
    def name(self) -> str:
        return _STANDARD_STAGE

    def run(self, context: ExperimentContext) -> StageResult:
        report = StrategyBuilderService(self._source).run(self._request)
        if report.dataset_version != self._expected_dataset_version:
            raise StrategyBuilderError(
                "Strategy Builder report dataset does not match the experiment definition"
            )
        self.report = report
        return StageResult(
            stage_name=self.name,
            outputs=_strategy_report_payload(report),
            warnings=report.comparison.warnings,
        )


class _EntrySweepStage:
    def __init__(
        self,
        source: StrategyBuilderSource,
        request: StrategyBuilderRequest,
        *,
        expected_dataset_version: str,
        target_feature_name: str,
        parameter: EntrySweepParameter,
        values: tuple[float, ...],
    ) -> None:
        self._source = source
        self._request = request
        self._expected_dataset_version = expected_dataset_version
        self._target_feature_name = target_feature_name
        self._parameter = parameter
        self._values = values
        self.report: StrategyBuilderEntrySweepReport | None = None

    @property
    def name(self) -> str:
        return _ENTRY_SWEEP_STAGE

    def run(self, context: ExperimentContext) -> StageResult:
        report = StrategyBuilderEntrySweepService(self._source).run(
            self._request,
            target_feature_name=self._target_feature_name,
            parameter=self._parameter,
            values=self._values,
        )
        if report.dataset_version != self._expected_dataset_version:
            raise StrategyBuilderError(
                "entry-sweep dataset does not match the experiment definition"
            )
        self.report = report
        return StageResult(
            stage_name=self.name,
            outputs=_entry_sweep_report_payload(report),
            warnings=(
                (
                    "Entry-parameter sweep is exploratory and does not validate the best observed "
                    "cell."
                ),
                "Each declared entry value may create a different point-in-time event population.",
            ),
        )


def attach_experiment_record_html(html: str, manifest: ExperimentManifest) -> str:
    """Add a compact persisted-experiment identity card to a Strategy Builder page."""

    marker = "</div></body></html>"
    if marker not in html:
        raise RuntimeError("Strategy Builder renderer omitted its closing application marker")
    checksum = manifest.manifest_checksum or "pending-verification"
    card = (
        '<div class="card" id="experiment-record">\n'
        "<h2>Saved experiment record</h2>\n"
        '<div class="section-note"><strong>Automatically saved:</strong> this run is now part of '
        "the durable SCOUT research record rather than only this browser page. Future Experiment "
        "Library / research-brain views can index this same record.</div>\n"
        "<table>"
        f"<tr><th>Experiment ID</th><td><code>{escape(manifest.experiment_id)}</code></td></tr>"
        f"<tr><th>Status</th><td>{escape(manifest.status.value)}</td></tr>"
        f"<tr><th>Research mode</th><td>{escape(manifest.definition.mode.value)}</td></tr>"
        "<tr><th>Dataset</th><td><code>"
        f"{escape(manifest.definition.dataset_version)}</code></td></tr>"
        f"<tr><th>Manifest checksum</th><td><code>{escape(checksum)}</code></td></tr>"
        "</table>\n</div>"
    )
    return html.replace(marker, card + marker, 1)


def _strategy_request_configuration(request: StrategyBuilderRequest) -> dict[str, JSONValue]:
    return {
        "surface": "visual_strategy_builder",
        "research_state": "EXPLORATORY",
        "provider_calls_made": False,
        "universe": {
            "universe_id": request.universe_id,
            "point_in_time_membership_claimed": False,
        },
        "historical_lookback_years": request.lookback_years,
        "outcome": {
            "maximum_holding_period_sessions": request.horizon,
            "forced_exit_at_maximum_holding_period": True,
            "maximum_holding_period_role": "research_backstop_and_control",
        },
        "entry": {
            "family": request.entry_family.value,
            "preset_id": request.preset_id,
            "expression": request.expression,
            "visual_conditions": [
                {
                    "feature_name": item.feature_name,
                    "operator": item.operator.value,
                    "value": item.value,
                    "join": item.join.value,
                }
                for item in request.visual_conditions
            ],
            "consolidation_duration_sessions": request.duration,
            "consolidation_max_range_percent": request.max_range_pct * 100.0,
            "trend_filter": request.trend_filter.value,
            "minimum_breakout_volume_ratio": request.min_breakout_volume_ratio,
        },
        "selection": {
            "rank_feature": request.rank_feature,
            "rank_direction": "descending" if request.descending else "ascending",
            "per_session_limit": request.per_session_limit,
        },
        "exit_candidates": {
            "hold_to_horizon_control": True,
            "same_bar_stop_target_policy": request.same_bar_policy.value,
            "managed_exit_plans": [_managed_plan_payload(item) for item in request.managed_exit_plans],
            "legacy_stop_grid_used": not bool(request.managed_exit_plans),
            "fixed_stop_percentages": [value * 100.0 for value in request.fixed_percentages],
            "trailing_stop_percentages": [value * 100.0 for value in request.trailing_percentages],
            "atr_stop_multiples": list(request.atr_multiples),
            "trailing_atr_multiples": list(request.trailing_atr_multiples),
            "partial_position_exits_supported": False,
        },
        "execution_costs_bps": {
            "entry_slippage": request.entry_slippage_bps,
            "normal_exit_slippage": request.exit_slippage_bps,
            "additional_stop_slippage": request.stop_slippage_bps,
            "commission_per_side": request.commission_bps_per_side,
        },
    }


def _managed_plan_payload(plan: ManagedExitPlan) -> dict[str, JSONValue]:
    return {
        "stop_family": plan.stop_family.value,
        "stop_value": plan.stop_value,
        "target_family": None if plan.target_family is None else plan.target_family.value,
        "target_value": plan.target_value,
        "same_bar_policy": plan.same_bar_policy.value,
    }


def _strategy_report_payload(report: StrategyBuilderReport) -> dict[str, JSONValue]:
    return {
        "schema_version": "strategy-builder-result-v0.2",
        "application_version": report.application_version,
        "research_state": report.research_state,
        "provider_calls_made": report.provider_calls_made,
        "dataset_version": report.dataset_version,
        "universe_id": report.universe_id,
        "universe_label": report.universe_label,
        "analysis_start": report.analysis_start.isoformat(),
        "analysis_end": report.analysis_end.isoformat(),
        "entry_family": report.entry_option.family.value,
        "entry_definition_version": report.entry_definition_version,
        "entry_event_count": report.entry_event_count,
        "complete_event_count": report.comparison.complete_event_count,
        "event_population_fingerprint": report.comparison.event_population_fingerprint,
        "comparison_definition_version": report.comparison.comparison_definition_version,
        "policies": [_policy_summary_payload(item) for item in report.comparison.policy_summaries],
        "performance": {
            "dataset_daily_bar_count": report.performance.dataset_daily_bar_count,
            "canonical_daily_bar_count": report.performance.canonical_daily_bar_count,
            "working_daily_bar_count": report.performance.working_daily_bar_count,
            "phase_seconds": [
                {"phase": phase, "seconds": seconds}
                for phase, seconds in report.performance.phase_seconds
            ],
            "total_seconds": report.performance.total_seconds,
            "version": report.performance.version,
        },
    }


def _policy_summary_payload(item: ExitPolicySummary) -> dict[str, JSONValue]:
    return {
        "policy_id": item.policy_id,
        "policy_version": item.policy_version,
        "family": item.family.value,
        "resolved_parameters": dict(item.resolved_parameters),
        "target_family": None if item.target_family is None else item.target_family.value,
        "target_parameters": dict(item.target_parameters),
        "sample_size": item.sample_size,
        "stop_out_count": item.stop_out_count,
        "stop_out_rate": item.stop_out_rate,
        "target_hit_count": item.target_hit_count,
        "target_hit_rate": item.target_hit_rate,
        "same_bar_ambiguous_count": item.same_bar_ambiguous_count,
        "same_bar_ambiguous_rate": item.same_bar_ambiguous_rate,
        "expectancy_return": item.expectancy,
        "expectancy_delta_vs_hold_return": item.expectancy_delta_vs_hold,
        "median_return": item.median_return,
        "win_probability": item.win_probability,
        "average_winner_return": item.average_winner,
        "average_loser_return": item.average_loser,
        "payoff_ratio": item.payoff_ratio,
        "profit_factor": item.profit_factor,
        "tail_loss_p05_return": item.tail_loss_p05,
        "average_holding_period_sessions": item.average_holding_period_sessions,
        "median_holding_period_sessions": item.median_holding_period_sessions,
        "median_mae_before_exit_return": item.median_mae_before_exit,
        "median_mfe_full_horizon_return": item.median_mfe_full_horizon,
        "median_max_drawdown_before_exit_return": item.median_max_drawdown_before_exit,
        "gap_through_frequency": item.gap_through_frequency,
        "mean_gap_loss_percent": item.mean_gap_loss_pct,
        "mean_cost_drag_return": item.mean_cost_drag_return,
    }


def _entry_sweep_report_payload(report: StrategyBuilderEntrySweepReport) -> dict[str, JSONValue]:
    return {
        "schema_version": "strategy-builder-entry-sweep-result-v0.1",
        "definition_version": report.definition_version,
        "research_state": report.research_state,
        "dataset_version": report.dataset_version,
        "analysis_start": report.analysis_start.isoformat(),
        "analysis_end": report.analysis_end.isoformat(),
        "target_feature_name": report.target_feature_name,
        "parameter": report.parameter.value,
        "parameter_label": report.parameter_label,
        "unit_label": report.unit_label,
        "declared_values": list(report.values),
        "search_space_fingerprint": report.search_space_fingerprint,
        "total_seconds": report.total_seconds,
        "points": [
            {
                "value": item.value,
                "resolved_feature_name": item.resolved_feature_name,
                "entry_event_count": item.entry_event_count,
                "complete_event_count": item.complete_event_count,
                "expectancy_return": item.expectancy,
                "win_probability": item.win_probability,
                "profit_factor": item.profit_factor,
                "tail_loss_p05_return": item.tail_loss_p05,
                "average_holding_period_sessions": item.average_holding_period_sessions,
            }
            for item in report.points
        ],
    }


__all__ = [
    "RecordedEntrySweepRun",
    "RecordedStrategyBuilderRun",
    "StrategyBuilderExperimentRecorder",
    "attach_experiment_record_html",
]
