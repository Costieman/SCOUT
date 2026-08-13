"""Private-workspace execution boundary for the complete Experiment A T0-T6 batch.

The operator layer connects one immutable canonical dataset to the governed Experiment A planner,
runner, integrity-preserving manifest store, and descriptive comparison output. It deliberately
supports only a fixed reviewed cohort in this first executable slice. That cohort is useful for
exploratory engineering/research, but it is not historical index membership and must not be described
as survivorship-bias-free validation evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, CanonicalDatasetManifest
from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.experiments.batch import (
    BatchExecutionSummary,
    BatchFailurePolicy,
    ExperimentBatchExecutor,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.trend_baseline import (
    CanonicalTrendBaselineSource,
    ExperimentATrendBaselineStage,
)
from trade_scout.experiments.trend_baseline_batch import (
    ExperimentABatchConfig,
    ExperimentAComparisonRow,
    compare_experiment_a_outputs,
    plan_experiment_a_batch,
)
from trade_scout.features.trend_context import TrendContext

FIXED_REVIEWED_COHORT_UNIVERSE_VERSION = "reviewed-canonical-fixed-cohort-v0.1"
FIXED_REVIEWED_COHORT_SCOPE_WARNING = (
    "Exploratory fixed reviewed cohort only; constituents are not historical index membership and "
    "results are not survivorship-bias-free validation evidence."
)


class ExperimentAOperatorError(RuntimeError):
    """Raised when the private-workspace Experiment A run cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class ExperimentAPreflight:
    """Verified canonical inputs and explicit scope limitations before batch execution."""

    dataset_version: str
    canonical_content_sha256: str
    universe_version: str
    benchmark_instrument_id: InstrumentId
    research_instrument_ids: tuple[InstrumentId, ...]
    record_count: int
    first_trade_date: date
    last_trade_date: date
    scope_warning: str = FIXED_REVIEWED_COHORT_SCOPE_WARNING


@dataclass(frozen=True, slots=True)
class ExperimentAOperatorResult:
    """Terminal batch state plus comparison rows when every T0-T6 child succeeds."""

    preflight: ExperimentAPreflight
    batch: BatchExecutionSummary
    comparison: tuple[ExperimentAComparisonRow, ...]

    @property
    def succeeded(self) -> bool:
        return self.batch.complete and self.batch.failed_count == 0 and self.batch.succeeded_count == 7


class FixedCohortEligibilityResolver:
    """Time-invariant eligibility for a predeclared exploratory research cohort.

    This resolver introduces no date-varying index membership claim. An instrument is eligible on a
    date only if it belongs to the cohort; the canonical source still provides bars only on dates for
    which the immutable dataset contains observations. The fixed cohort itself may embody ex-post
    selection and is therefore unsuitable as confirmatory survivorship-bias-free evidence.
    """

    def __init__(self, instrument_ids: tuple[InstrumentId, ...], *, universe_version: str) -> None:
        if not universe_version.strip():
            raise ValueError("universe_version must be non-empty")
        keys = tuple(str(item) for item in instrument_ids)
        if not keys:
            raise ValueError("fixed cohort requires at least one research instrument")
        if len(set(keys)) != len(keys):
            raise ValueError("fixed cohort instrument IDs must be unique")
        self._instrument_ids = frozenset(keys)
        self._universe_version = universe_version

    @property
    def universe_version(self) -> str:
        return self._universe_version

    def is_eligible(self, instrument_id: InstrumentId, trade_date: date) -> bool:
        del trade_date
        return str(instrument_id) in self._instrument_ids


def preflight_experiment_a_fixed_cohort(
    store: CanonicalDailyBarStore,
    *,
    dataset_version: DatasetVersion,
    benchmark_instrument_id: InstrumentId,
    universe_version: str = FIXED_REVIEWED_COHORT_UNIVERSE_VERSION,
) -> ExperimentAPreflight:
    """Verify one immutable canonical dataset and derive its explicit fixed research cohort."""

    manifest = store.get_manifest(dataset_version)
    if manifest is None:
        raise ExperimentAOperatorError(f"canonical dataset {dataset_version} is not registered")
    _require_pass_manifest(manifest)

    bars = store.load(dataset_version)
    benchmark_key = str(benchmark_instrument_id)
    observed_ids = tuple(sorted({str(bar.instrument_id) for bar in bars}))
    if benchmark_key not in observed_ids:
        raise ExperimentAOperatorError(
            "Experiment A T6 requires the explicit benchmark to exist inside the same immutable "
            f"canonical dataset; missing benchmark instrument_id={benchmark_key}"
        )

    research_ids = tuple(InstrumentId(value) for value in observed_ids if value != benchmark_key)
    if not research_ids:
        raise ExperimentAOperatorError("canonical dataset contains no research instruments besides benchmark")

    return ExperimentAPreflight(
        dataset_version=str(dataset_version),
        canonical_content_sha256=manifest.content_checksum_sha256,
        universe_version=universe_version,
        benchmark_instrument_id=benchmark_instrument_id,
        research_instrument_ids=research_ids,
        record_count=manifest.record_count,
        first_trade_date=manifest.first_trade_date,
        last_trade_date=manifest.last_trade_date,
    )


def execute_experiment_a_fixed_cohort(
    store: CanonicalDailyBarStore,
    manifest_store: FileManifestStore,
    *,
    dataset_version: DatasetVersion,
    benchmark_instrument_id: InstrumentId,
    code_version: str,
    config_schema_version: str,
    outcome_horizons: tuple[int, ...] = (5, 10, 20, 40, 60, 120, 252),
    sampling_stride: int = 5,
    sma_slope_lookback: int = 20,
    trailing_return_intervals: int = 60,
    relative_strength_intervals: int = 60,
    universe_version: str = FIXED_REVIEWED_COHORT_UNIVERSE_VERSION,
) -> ExperimentAOperatorResult:
    """Execute all seven governed trend contexts against one verified fixed canonical cohort."""

    preflight = preflight_experiment_a_fixed_cohort(
        store,
        dataset_version=dataset_version,
        benchmark_instrument_id=benchmark_instrument_id,
        universe_version=universe_version,
    )
    eligibility = FixedCohortEligibilityResolver(
        preflight.research_instrument_ids,
        universe_version=preflight.universe_version,
    )
    source = CanonicalTrendBaselineSource(
        store,
        eligibility,
        benchmark_instrument_id=benchmark_instrument_id,
    )
    config = ExperimentABatchConfig(
        dataset_version=preflight.dataset_version,
        universe_version=preflight.universe_version,
        code_version=_required_text(code_version, "code_version"),
        config_schema_version=_required_text(config_schema_version, "config_schema_version"),
        outcome_horizons=outcome_horizons,
        sampling_stride=sampling_stride,
        sma_slope_lookback=sma_slope_lookback,
        trailing_return_intervals=trailing_return_intervals,
        relative_strength_intervals=relative_strength_intervals,
    )
    plan = plan_experiment_a_batch(config)
    runner = ExperimentRunner(manifest_store)
    executor = ExperimentBatchExecutor(runner)
    batch = executor.execute(
        plan,
        lambda definition: (ExperimentATrendBaselineStage(source),),
        failure_policy=BatchFailurePolicy.CONTINUE,
    )
    if not batch.complete or batch.failed_count:
        raise ExperimentAOperatorError(_batch_failure_message(batch))

    experiment_ids_by_context: dict[TrendContext, str] = {}
    for child, record in zip(plan.children, batch.records, strict=True):
        configuration = child.definition.resolved_configuration.get("experiment_a")
        if not isinstance(configuration, dict):
            raise ExperimentAOperatorError("planned Experiment A child is missing resolved configuration")
        raw_context = configuration.get("trend_context")
        if not isinstance(raw_context, str):
            raise ExperimentAOperatorError("planned Experiment A child is missing trend context")
        experiment_ids_by_context[TrendContext(raw_context)] = record.experiment_id

    comparison = compare_experiment_a_outputs(experiment_ids_by_context, manifest_store)
    return ExperimentAOperatorResult(preflight=preflight, batch=batch, comparison=comparison)


def _require_pass_manifest(manifest: CanonicalDatasetManifest) -> None:
    quality = manifest.quality_summary
    if quality.warn_count or quality.quarantine_count or quality.reject_count:
        raise ExperimentAOperatorError(
            "Experiment A requires an all-PASS canonical dataset; "
            f"warn={quality.warn_count}, quarantine={quality.quarantine_count}, "
            f"reject={quality.reject_count}"
        )
    if quality.pass_count != manifest.record_count:
        raise ExperimentAOperatorError("canonical manifest PASS count does not equal record count")


def _batch_failure_message(batch: BatchExecutionSummary) -> str:
    failures = tuple(
        f"{record.label}: {record.failure_message or record.status.value}"
        for record in batch.records
        if record.status.value != "SUCCEEDED"
    )
    detail = "; ".join(failures) if failures else "batch did not execute the complete T0-T6 plan"
    return f"Experiment A batch failed closed: {detail}"


def _required_text(value: str, field: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must be non-empty")
    return stripped
