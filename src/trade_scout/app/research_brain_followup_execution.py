"""Execute fully specified approved Research Brain follow-up proposals.

Executor v1 deliberately supports one scientifically explicit path: a same-instrument randomized
eligible-timing comparator for a frozen feature-expression Strategy Builder definition. The
operator must still press the execution button and, for a source parameter sweep, explicitly freeze
one already-declared candidate value. Execution runs through the normal ExperimentRunner, persists
a child experiment, and appends that terminal result back to the same brain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.research_brain_followups import (
    FileResearchBrainFollowUpStore,
    FollowUpKind,
    ResearchBrainFollowUpError,
)
from trade_scout.app.strategy_builder_configuration import (
    freeze_entry_sweep_candidate,
    source_declared_entry_sweep_values,
    strategy_request_from_resolved_configuration,
)
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.strategy_builder_service import (
    StrategyBuilderError,
    StrategyBuilderRequest,
    StrategyBuilderService,
    StrategyBuilderSource,
    WindowedStrategyBuilderSource,
)
from trade_scout.data.contracts import DailyBar, PriceRepresentation, ResearchBar, to_research_bar
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentManifest,
    ExperimentStatus,
    JSONValue,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.registry import DuckDBExperimentRegistry, IndexedManifestStore
from trade_scout.experiments.research_brains import FileResearchBrainStore, ResearchBrainError
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.serialization import canonical_json, sha256_json
from trade_scout.experiments.store import FileManifestStore
from trade_scout.features.parameterized_expression import extract_parameterized_specs
from trade_scout.features.parameterized_indicators import compute_parameterized_indicator_frame
from trade_scout.risk.initial_stops import CostModel
from trade_scout.statistics.random_timing_control import run_same_instrument_random_timing_control
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    required_strategy_warmup_observations,
    run_feature_strategy_research,
)

_COMPARATOR_KIND = "same_instrument_random_eligible_timing"
_ITERATIONS = 1000


class ResearchBrainFollowUpExecutionError(RuntimeError):
    """Raised when an approved follow-up cannot be executed without changing its scientific plan."""


@dataclass(frozen=True, slots=True)
class ResearchBrainFollowUpExecution:
    """Immutable receipt binding proposal approval to one terminal child experiment."""

    execution_id: str
    brain_id: str
    proposal_id: str
    proposal_checksum: str
    approval_id: str
    approval_checksum: str
    executed_at: str
    executed_by: str
    execution_kind: str
    execution_inputs: dict[str, JSONValue]
    result_experiment_id: str
    result_manifest_checksum: str
    result_status: ExperimentStatus
    auto_attached_to_brain: bool
    version: str = "research-brain-follow-up-execution-v0.1"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("execution_id", self.execution_id),
            ("brain_id", self.brain_id),
            ("proposal_id", self.proposal_id),
            ("proposal_checksum", self.proposal_checksum),
            ("approval_id", self.approval_id),
            ("approval_checksum", self.approval_checksum),
            ("executed_by", self.executed_by),
            ("execution_kind", self.execution_kind),
            ("result_experiment_id", self.result_experiment_id),
            ("result_manifest_checksum", self.result_manifest_checksum),
            ("version", self.version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        _aware_timestamp(self.executed_at)
        if self.result_status not in {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED}:
            raise ValueError("follow-up execution receipt requires a terminal experiment status")


class FileResearchBrainFollowUpExecutionStore:
    """Append-only checksum-verified execution receipts colocated with each research brain."""

    def __init__(self, brain_root: Path) -> None:
        self._brain_root = brain_root

    def write(self, receipt: ResearchBrainFollowUpExecution) -> ResearchBrainFollowUpExecution:
        path = self._path(receipt.brain_id, receipt.proposal_id)
        if path.exists():
            existing = self.read(receipt.brain_id, receipt.proposal_id)
            if existing != receipt:
                raise ResearchBrainFollowUpExecutionError(
                    "follow-up execution receipt already exists with different content"
                )
            return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(path, {"execution": receipt, "checksum": sha256_json(receipt)})
        return receipt

    def read(self, brain_id: str, proposal_id: str) -> ResearchBrainFollowUpExecution:
        path = self._path(brain_id, proposal_id)
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            payload = cast(dict[str, object], raw["execution"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainFollowUpExecutionError(
                f"cannot read follow-up execution receipt: {brain_id}/{proposal_id}"
            ) from exc
        receipt = _receipt_from_mapping(payload)
        if receipt.brain_id != brain_id or receipt.proposal_id != proposal_id:
            raise ResearchBrainFollowUpExecutionError("follow-up execution receipt identity mismatch")
        if sha256_json(receipt) != expected:
            raise ResearchBrainFollowUpExecutionError(
                f"follow-up execution receipt checksum mismatch: {brain_id}/{proposal_id}"
            )
        return receipt

    def read_optional(
        self,
        brain_id: str,
        proposal_id: str,
    ) -> ResearchBrainFollowUpExecution | None:
        path = self._path(brain_id, proposal_id)
        return None if not path.exists() else self.read(brain_id, proposal_id)

    def list(self, brain_id: str) -> tuple[ResearchBrainFollowUpExecution, ...]:
        root = self._brain_root / brain_id / "proposal-executions"
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (self.read(brain_id, path.stem) for path in root.glob("*.json")),
                key=lambda item: (item.executed_at, item.execution_id),
            )
        )

    def _path(self, brain_id: str, proposal_id: str) -> Path:
        _safe_identifier(brain_id, "brain_id")
        _safe_identifier(proposal_id, "proposal_id")
        return self._brain_root / brain_id / "proposal-executions" / f"{proposal_id}.json"


@dataclass(frozen=True, slots=True)
class ResearchBrainComparatorExecutor:
    """Run one approved comparator proposal and attach its terminal child experiment to the brain."""

    brain_root: Path
    recorder: StrategyBuilderExperimentRecorder
    source: StrategyBuilderSource

    def execute(
        self,
        *,
        brain_id: str,
        proposal_id: str,
        executed_by: str,
        candidate_value: float | None = None,
        executed_at: datetime | None = None,
    ) -> ResearchBrainFollowUpExecution:
        actor = executed_by.strip()
        if not actor:
            raise ValueError("executed_by must be non-empty")
        execution_store = FileResearchBrainFollowUpExecutionStore(self.brain_root)
        existing = execution_store.read_optional(brain_id, proposal_id)
        if existing is not None:
            return existing

        brain_store = FileResearchBrainStore(self.brain_root)
        view = _brain_view_for_preflight(
            brain_store,
            self.recorder.experiment_root,
            brain_id,
        )
        follow_up_store = FileResearchBrainFollowUpStore(self.brain_root)
        proposal = follow_up_store.read_proposal(brain_id, proposal_id)
        approval = follow_up_store.read_approval_optional(brain_id, proposal_id)
        if approval is None:
            raise ResearchBrainFollowUpExecutionError(
                "follow-up proposal must be explicitly approved before execution"
            )
        if not follow_up_store.matches_current_state(proposal, view):
            raise ResearchBrainFollowUpExecutionError(
                "approved follow-up proposal is stale because the brain evidence changed"
            )
        if proposal.kind is not FollowUpKind.COMPARATOR:
            raise ResearchBrainFollowUpExecutionError(
                f"executor v1 supports comparator proposals only, not {proposal.kind.value}"
            )

        source_store = FileManifestStore(self.recorder.experiment_root)
        source_manifest = source_store.read_manifest(proposal.source_experiment_id)
        if source_manifest.status is not ExperimentStatus.SUCCEEDED:
            raise ResearchBrainFollowUpExecutionError("source experiment is no longer successful")
        if source_manifest.manifest_checksum != proposal.source_experiment_manifest_checksum:
            raise ResearchBrainFollowUpExecutionError(
                "source experiment checksum no longer matches the approved proposal"
            )
        if source_manifest.definition.dataset_version != self.recorder.dataset_version:
            raise ResearchBrainFollowUpExecutionError(
                "source experiment dataset is not the workbench's currently selected immutable dataset"
            )
        configuration = source_manifest.definition.resolved_configuration
        request = strategy_request_from_resolved_configuration(configuration)
        declared_values = source_declared_entry_sweep_values(configuration)
        resolved_candidate: float | None = None
        if declared_values:
            if candidate_value is None:
                raise ResearchBrainFollowUpExecutionError(
                    "source is a parameter sweep; choose one already-declared candidate value before "
                    "running the comparator"
                )
            resolved_candidate = float(candidate_value)
            request = freeze_entry_sweep_candidate(configuration, request, resolved_candidate)
        elif candidate_value is not None:
            raise ResearchBrainFollowUpExecutionError(
                "candidate_value applies only when the source experiment is an entry sweep"
            )
        if request.entry_family is not EntryFamily.FEATURE_EXPRESSION:
            raise ResearchBrainFollowUpExecutionError(
                "same-instrument random timing comparator currently supports feature-expression "
                "entries only"
            )
        if not isinstance(self.source, WindowedStrategyBuilderSource):
            raise ResearchBrainFollowUpExecutionError(
                "comparator execution requires the window-aware canonical Strategy Builder source"
            )

        timestamp = executed_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")
        seed = int(sha256_json({"proposal_id": proposal_id, "candidate": resolved_candidate})[:8], 16)
        execution_inputs: dict[str, JSONValue] = {
            "comparator_kind": _COMPARATOR_KIND,
            "candidate_value": resolved_candidate,
            "iterations": _ITERATIONS,
            "random_seed": seed,
        }
        execution_id = "brainexec_" + sha256_json(
            {
                "proposal_checksum": sha256_json(proposal),
                "approval_checksum": sha256_json(approval),
                "execution_inputs": execution_inputs,
            }
        )[:24]
        experiment_id = "exp_" + execution_id
        manifest = self._run_or_recover_child(
            experiment_id=experiment_id,
            proposal_id=proposal_id,
            proposal_checksum=sha256_json(proposal),
            approval_id=approval.approval_id,
            approval_checksum=sha256_json(approval),
            source_manifest=source_manifest,
            request=request,
            candidate_value=resolved_candidate,
            seed=seed,
        )
        _attach_terminal_manifest(
            brain_store,
            brain_id=brain_id,
            manifest=manifest,
            added_by=actor,
            proposal_id=proposal_id,
        )
        checksum = manifest.manifest_checksum
        if checksum is None:
            raise ResearchBrainFollowUpExecutionError(
                "terminal follow-up experiment is missing its verified manifest checksum"
            )
        receipt = ResearchBrainFollowUpExecution(
            execution_id=execution_id,
            brain_id=brain_id,
            proposal_id=proposal_id,
            proposal_checksum=sha256_json(proposal),
            approval_id=approval.approval_id,
            approval_checksum=sha256_json(approval),
            executed_at=timestamp.astimezone(UTC).isoformat(),
            executed_by=actor,
            execution_kind="COMPARATOR_RANDOM_TIMING",
            execution_inputs=execution_inputs,
            result_experiment_id=manifest.experiment_id,
            result_manifest_checksum=checksum,
            result_status=manifest.status,
            auto_attached_to_brain=True,
        )
        return execution_store.write(receipt)

    def _run_or_recover_child(
        self,
        *,
        experiment_id: str,
        proposal_id: str,
        proposal_checksum: str,
        approval_id: str,
        approval_checksum: str,
        source_manifest: ExperimentManifest,
        request: StrategyBuilderRequest,
        candidate_value: float | None,
        seed: int,
    ) -> ExperimentManifest:
        raw_store = FileManifestStore(self.recorder.experiment_root)
        try:
            existing = raw_store.read_manifest(experiment_id)
        except (OSError, ValueError, KeyError):
            existing = None
        if existing is not None:
            if existing.status not in {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED}:
                raise ResearchBrainFollowUpExecutionError(
                    f"existing deterministic follow-up experiment {experiment_id} is not terminal"
                )
            return existing

        configuration = dict(source_manifest.definition.resolved_configuration)
        configuration.pop("research_variable", None)
        configuration["research_brain_follow_up"] = {
            "proposal_id": proposal_id,
            "proposal_checksum": proposal_checksum,
            "approval_id": approval_id,
            "approval_checksum": approval_checksum,
            "source_experiment_id": source_manifest.experiment_id,
            "source_experiment_manifest_checksum": source_manifest.manifest_checksum,
            "challenge": "same_instrument_random_eligible_timing",
            "candidate_value": candidate_value,
            "iterations": _ITERATIONS,
            "random_seed": seed,
            "auto_attach_result_to_brain": True,
        }
        definition = ExperimentDefinition(
            name="Research Brain follow-up — randomized timing comparator",
            hypothesis=(
                "The frozen source entry timing adds information beyond count-matched randomized "
                "eligible timing on the same instruments."
            ),
            mode=ResearchMode.EXPLORATORY,
            dataset_version=self.recorder.dataset_version,
            universe_version=self.recorder.universe_version,
            code_version=self.recorder.code_version,
            config_schema_version="research-brain-follow-up-execution-v0.1",
            resolved_configuration=configuration,
            parent_experiment_id=source_manifest.experiment_id,
        )
        stage = _RandomTimingComparatorStage(
            self.source,
            request,
            expected_dataset_version=self.recorder.dataset_version,
            iterations=_ITERATIONS,
            random_seed=seed,
        )
        registry = DuckDBExperimentRegistry(self.recorder.registry_path)
        store = IndexedManifestStore(raw_store, registry)
        runner = ExperimentRunner(store, id_factory=lambda: experiment_id)
        try:
            return runner.run(definition, (stage,))
        except ExperimentExecutionError as exc:
            return raw_store.read_manifest(exc.experiment_id)


@dataclass(slots=True)
class _RandomTimingComparatorStage:
    source: StrategyBuilderSource
    request: StrategyBuilderRequest
    expected_dataset_version: str
    iterations: int
    random_seed: int

    @property
    def name(self) -> str:
        return "research_brain_random_timing_comparator"

    def run(self, context: ExperimentContext) -> StageResult:
        report = StrategyBuilderService(self.source).run(self.request)
        if report.dataset_version != self.expected_dataset_version:
            raise StrategyBuilderError("follow-up comparator dataset mismatch")
        feature_report = report.feature_strategy_report
        if feature_report is None:
            raise StrategyBuilderError(
                "random-timing comparator requires a feature-expression source population"
            )
        if not isinstance(self.source, WindowedStrategyBuilderSource):
            raise StrategyBuilderError("random-timing comparator requires a window-aware source")
        strategy = StrategyDefinition(
            strategy_id="research-brain-frozen-comparator-source",
            name="Research Brain frozen comparator source",
            expression=self.request.expression,
            rank_feature=self.request.rank_feature,
            descending=self.request.descending,
            per_session_limit=self.request.per_session_limit,
            description="Frozen source entry definition used by an approved Research Brain follow-up.",
        )
        specs = extract_parameterized_specs(strategy.expression)
        fixed_warmup = required_strategy_warmup_observations(strategy)
        parameterized_warmup = max(
            (item.minimum_observations for item in specs),
            default=1,
        )
        daily_bars = self.source.strategy_builder_daily_bars(
            self.request.universe_id,
            signal_start=report.analysis_start,
            signal_end=report.analysis_end,
            warmup_observations=max(fixed_warmup, parameterized_warmup),
        )
        extra_features = compute_parameterized_indicator_frame(daily_bars, specs)
        rebuilt = run_feature_strategy_research(
            daily_bars,
            strategy=strategy,
            horizons=(self.request.horizon,),
            signal_start=report.analysis_start,
            signal_end=report.analysis_end,
            extra_features=extra_features,
            measure_outcomes=False,
        )
        if tuple(
            (item.instrument_id, item.signal_date, item.signal_index) for item in rebuilt.signals
        ) != tuple(
            (item.instrument_id, item.signal_date, item.signal_index)
            for item in feature_report.signals
        ):
            raise RuntimeError(
                "follow-up comparator could not reproduce the frozen Strategy Builder signal population"
            )
        research_by_instrument = _research_by_instrument(daily_bars)
        control = run_same_instrument_random_timing_control(
            research_by_instrument,
            tuple(rebuilt.signals),
            horizon=self.request.horizon,
            cost_model=CostModel(
                entry_slippage_bps=self.request.entry_slippage_bps,
                exit_slippage_bps=self.request.exit_slippage_bps,
                stop_slippage_bps=self.request.stop_slippage_bps,
                commission_bps_per_side=self.request.commission_bps_per_side,
            ),
            signal_start=report.analysis_start,
            signal_end=report.analysis_end,
            iterations=self.iterations,
            random_seed=self.random_seed,
        )
        hold = next(
            (
                item
                for item in report.comparison.policy_summaries
                if item.family.value == "hold_to_horizon"
            ),
            None,
        )
        if hold is None or hold.expectancy is None:
            raise RuntimeError("frozen Strategy Builder report has no hold-to-horizon expectancy")
        if abs(hold.expectancy - control.strategy_mean_return) > 1e-12:
            raise RuntimeError(
                "random-timing control did not reproduce the source hold-to-horizon expectancy"
            )
        outputs: dict[str, JSONValue] = {
            "schema_version": "research-brain-random-timing-comparator-v0.1",
            "research_state": "EXPLORATORY",
            "provider_calls_made": False,
            "dataset_version": report.dataset_version,
            "analysis_start": report.analysis_start.isoformat(),
            "analysis_end": report.analysis_end.isoformat(),
            "comparator_kind": control.comparator_kind,
            "comparator_definition_version": control.comparator_definition_version,
            "complete_event_count": control.sample_size,
            "instrument_count": control.instrument_count,
            "eligible_timing_count": control.eligible_timing_count,
            "strategy_mean_return": control.strategy_mean_return,
            "random_timing_baseline_mean_return": control.random_timing_mean_return,
            "excess_vs_random_timing": control.excess_vs_random_timing,
            "random_timing_null_interval": {
                "lower": control.null_interval_lower,
                "upper": control.null_interval_upper,
                "coverage": 0.95,
            },
            "p_value": control.one_sided_empirical_p_value,
            "iterations": control.iterations,
            "random_seed": control.random_seed,
        }
        return StageResult(
            stage_name=self.name,
            outputs=outputs,
            warnings=control.warnings,
        )


def _research_by_instrument(
    bars: tuple[DailyBar, ...],
) -> dict[str, tuple[ResearchBar, ...]]:
    grouped: dict[str, list[DailyBar]] = {}
    for bar in bars:
        grouped.setdefault(str(bar.instrument_id), []).append(bar)
    return {
        instrument_id: tuple(
            to_research_bar(
                item,
                representation=PriceRepresentation.SPLIT_ADJUSTED,
                eligibility=True,
            )
            for item in sorted(rows, key=lambda value: value.trade_date)
        )
        for instrument_id, rows in grouped.items()
    }


def _brain_view_for_preflight(
    brain_store: FileResearchBrainStore,
    experiment_root: Path,
    brain_id: str,
):
    from trade_scout.app.experiment_library_service import ExperimentLibraryService
    from trade_scout.app.research_brain_service import (
        ResearchBrainExperimentView,
        ResearchBrainView,
    )

    snapshot = brain_store.snapshot(brain_id)
    experiment_store = FileManifestStore(experiment_root)
    library = ExperimentLibraryService(experiment_root)
    experiments: list[ResearchBrainExperimentView] = []
    for membership in snapshot.memberships:
        try:
            manifest = experiment_store.read_manifest(membership.experiment_id)
            brain_store.verify_membership_experiment(brain_id, manifest)
            detail = library.detail(membership.experiment_id)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            experiments.append(
                ResearchBrainExperimentView(
                    membership=membership,
                    experiment=None,
                    integrity_error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        experiments.append(
            ResearchBrainExperimentView(
                membership=membership,
                experiment=detail,
                integrity_error=None,
            )
        )
    return ResearchBrainView(snapshot=snapshot, experiments=tuple(experiments))


def _attach_terminal_manifest(
    brain_store: FileResearchBrainStore,
    *,
    brain_id: str,
    manifest: ExperimentManifest,
    added_by: str,
    proposal_id: str,
) -> None:
    existing_ids = {item.experiment_id for item in brain_store.memberships(brain_id)}
    if manifest.experiment_id in existing_ids:
        return
    try:
        brain_store.add_experiment(
            brain_id,
            manifest,
            added_by=added_by,
            note=f"Automatic result of approved Research Brain proposal {proposal_id}.",
        )
    except ResearchBrainError as exc:
        raise ResearchBrainFollowUpExecutionError(str(exc)) from exc


def _receipt_from_mapping(raw: dict[str, object]) -> ResearchBrainFollowUpExecution:
    inputs = raw.get("execution_inputs", {})
    if not isinstance(inputs, dict):
        raise ResearchBrainFollowUpExecutionError("execution_inputs has invalid stored type")
    return ResearchBrainFollowUpExecution(
        execution_id=str(raw["execution_id"]),
        brain_id=str(raw["brain_id"]),
        proposal_id=str(raw["proposal_id"]),
        proposal_checksum=str(raw["proposal_checksum"]),
        approval_id=str(raw["approval_id"]),
        approval_checksum=str(raw["approval_checksum"]),
        executed_at=str(raw["executed_at"]),
        executed_by=str(raw["executed_by"]),
        execution_kind=str(raw["execution_kind"]),
        execution_inputs=cast(dict[str, JSONValue], inputs),
        result_experiment_id=str(raw["result_experiment_id"]),
        result_manifest_checksum=str(raw["result_manifest_checksum"]),
        result_status=ExperimentStatus(str(raw["result_status"])),
        auto_attached_to_brain=bool(raw["auto_attached_to_brain"]),
        version=str(raw.get("version", "research-brain-follow-up-execution-v0.1")),
    )


def _safe_identifier(value: str, field_name: str) -> None:
    if not value.strip() or any(character in value for character in "/\\"):
        raise ValueError(f"{field_name} must be a non-empty path-safe identifier")


def _aware_timestamp(value: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("executed_at must be an ISO timestamp") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("executed_at must be timezone-aware")
    return resolved


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "FileResearchBrainFollowUpExecutionStore",
    "ResearchBrainComparatorExecutor",
    "ResearchBrainFollowUpExecution",
    "ResearchBrainFollowUpExecutionError",
]
