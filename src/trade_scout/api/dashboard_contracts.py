"""Typed, provider-independent contracts for the Trade Scout user interface.

These objects carry already-computed application state to a replaceable presentation layer. They
contain no provider-native payloads and perform no feature, pattern, event, risk, statistics, or
ranking calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class HealthState(StrEnum):
    """User-visible validity state for data and operational prerequisites."""

    PASS = "PASS"
    WARN = "WARN"
    QUARANTINE = "QUARANTINE"
    BLOCKED = "BLOCKED"


class ResearchState(StrEnum):
    """Research-to-production lifecycle labels exposed by the application."""

    IDEA = "IDEA"
    EXPLORATORY = "EXPLORATORY"
    CANDIDATE = "CANDIDATE"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    PRODUCTION_ELIGIBLE = "PRODUCTION_ELIGIBLE"
    SCANNING = "SCANNING"
    MONITORING = "MONITORING"
    WATCH = "WATCH"
    REVIEW = "REVIEW"
    RETIRED = "RETIRED"


class WorkspaceState(StrEnum):
    """Whether a workspace can currently produce normal outputs."""

    AVAILABLE = "AVAILABLE"
    PREVIEW = "PREVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ProvenanceSummary:
    """Compact lineage panel required on important analytical views."""

    dataset_version: str | None
    strategy_version: str | None
    feature_set_version: str | None
    risk_policy_version: str | None
    ranking_model_version: str | None
    run_id: str | None
    as_of_date: date | None
    software_version: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderHealthSummary:
    """Provider-level status after ingestion/application services classify the result."""

    provider_id: str
    display_name: str
    role: str
    state: HealthState
    latest_successful_session: date | None
    message: str
    progress_current: int | None = None
    progress_total: int | None = None
    progress_label: str | None = None
    operational_status: str | None = None
    last_observed_at: datetime | None = None
    quota_pause_count: int | None = None
    failure_count: int | None = None
    last_rate_limited_symbol: str | None = None
    last_failed_symbol: str | None = None
    last_failure_type: str | None = None

    def __post_init__(self) -> None:
        if (self.progress_current is None) != (self.progress_total is None):
            raise ValueError("provider progress current and total must be supplied together")
        if self.progress_current is not None and self.progress_total is not None:
            if self.progress_current < 0 or self.progress_total < 0:
                raise ValueError("provider progress counts cannot be negative")
            if self.progress_current > self.progress_total:
                raise ValueError("provider progress current cannot exceed total")
        for value in (self.quota_pause_count, self.failure_count):
            if value is not None and value < 0:
                raise ValueError("provider operational counts cannot be negative")
        if self.last_observed_at is not None and (
            self.last_observed_at.tzinfo is None or self.last_observed_at.utcoffset() is None
        ):
            raise ValueError("provider last_observed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class QualityCounts:
    """Counts of canonical data-quality states for a selected dataset version."""

    passed: int
    warned: int
    quarantined: int

    def __post_init__(self) -> None:
        if min(self.passed, self.warned, self.quarantined) < 0:
            raise ValueError("quality counts cannot be negative")


@dataclass(frozen=True, slots=True)
class DataHealthSummary:
    """Data Health workspace summary supplied by data/application services."""

    state: HealthState
    dataset_version: str | None
    latest_canonical_session: date | None
    quality_counts: QualityCounts
    missing_data_anomaly_count: int | None
    cross_provider_discrepancy_count: int | None
    corporate_action_anomaly_count: int | None
    failed_ingestion_job_count: int | None
    scanner_freshness_gate: HealthState
    providers: tuple[ProviderHealthSummary, ...]
    message: str
    provenance: ProvenanceSummary
    review_work_item_count: int | None = None
    phase_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        counts = (
            self.missing_data_anomaly_count,
            self.cross_provider_discrepancy_count,
            self.corporate_action_anomaly_count,
            self.failed_ingestion_job_count,
            self.review_work_item_count,
        )
        if any(value is not None and value < 0 for value in counts):
            raise ValueError("data-health counts cannot be negative")


@dataclass(frozen=True, slots=True)
class ResearchLabSummary:
    """Research Lab availability and currently selected experiment context."""

    workspace_state: WorkspaceState
    strategy_family: str
    universe_label: str
    dataset_label: str
    research_mode: ResearchState
    resolved_configuration_id: str | None
    launch_enabled: bool
    blocking_reasons: tuple[str, ...]
    provenance: ProvenanceSummary

    def __post_init__(self) -> None:
        allowed_modes = {ResearchState.EXPLORATORY, ResearchState.VALIDATING}
        if self.research_mode not in allowed_modes:
            raise ValueError("Research Lab mode must be EXPLORATORY or VALIDATING")
        if self.launch_enabled and self.blocking_reasons:
            raise ValueError("launch cannot be enabled while blocking reasons exist")


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """Already-computed evidence displayed beside a scanner/candidate observation."""

    sample_size: int
    positive_outcome_fraction: float | None
    uncertainty_low: float | None
    uncertainty_high: float | None
    expectancy: float | None
    mae_median: float | None
    mfe_median: float | None

    def __post_init__(self) -> None:
        if self.sample_size < 0:
            raise ValueError("evidence sample size cannot be negative")
        for value in (
            self.positive_outcome_fraction,
            self.uncertainty_low,
            self.uncertainty_high,
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError("probability-like evidence values must be between zero and one")
        if (
            self.uncertainty_low is not None
            and self.uncertainty_high is not None
            and self.uncertainty_low > self.uncertainty_high
        ):
            raise ValueError("uncertainty interval is inverted")


@dataclass(frozen=True, slots=True)
class ScannerCandidateSummary:
    """Compact production-intelligence row; values are computed outside the UI."""

    instrument_id: str
    symbol: str
    company_name: str
    candidate_state: str
    strategy_version: str
    pattern_duration_sessions: int | None
    distance_to_trigger_fraction: float | None
    evidence: EvidenceSummary
    risk_summary: str
    data_freshness: HealthState
    transparent_rank_value: float | None
    provenance: ProvenanceSummary


@dataclass(frozen=True, slots=True)
class ScannerSummary:
    """Scanner workspace contract, including explicit freshness blocking."""

    workspace_state: WorkspaceState
    as_of_date: date | None
    freshness_gate: HealthState
    candidates: tuple[ScannerCandidateSummary, ...]
    blocking_reasons: tuple[str, ...]
    provenance: ProvenanceSummary

    def __post_init__(self) -> None:
        if self.workspace_state is WorkspaceState.BLOCKED and self.candidates:
            raise ValueError("blocked scanner must not expose normal candidate rows")


@dataclass(frozen=True, slots=True)
class ExperimentSummary:
    """Experiment-library row with immutable research identity and lineage."""

    experiment_id: str
    display_name: str
    strategy_family: str
    research_state: ResearchState
    dataset_version: str
    code_version: str
    parent_experiment_id: str | None
    completed_at: datetime | None
    decision: str


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    """One presentation-ready application snapshot for the low-fidelity client."""

    generated_at: datetime
    build_label: str
    active_phase: str
    data_health: DataHealthSummary
    research: ResearchLabSummary
    scanner: ScannerSummary
    experiments: tuple[ExperimentSummary, ...]
    global_notices: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("application snapshot generated_at must be timezone-aware")
