"""Stable contracts for scanner replay and later production scanning.

The scanner consumes fixed research outputs. These contracts deliberately carry provenance and
candidate state without providing any mechanism to tune research definitions or ranking weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import InstrumentId, QualityStatus
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionState
from trade_scout.validation.research_package import ResearchEvidencePackage

SnapshotScalar = str | int | float | bool | None


class ScannerMode(StrEnum):
    """Operational modes declared by the Scanner & Ranking specification."""

    END_OF_DAY = "END_OF_DAY"
    INTRADAY = "INTRADAY"
    RESEARCH_PREVIEW = "RESEARCH_PREVIEW"
    REPLAY = "REPLAY"


class ReplayPublicationClass(StrEnum):
    """Whether replay represents a production-eligible or research-preview strategy."""

    PRODUCTION_COMPATIBLE = "PRODUCTION_COMPATIBLE"
    RESEARCH_PREVIEW = "RESEARCH_PREVIEW"


class ScanCandidateState(StrEnum):
    """Lifecycle states exposed by the scanner contract."""

    FORMING = "FORMING"
    QUALIFIED = "QUALIFIED"
    TRIGGER_READY = "TRIGGER_READY"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"
    COOLDOWN = "COOLDOWN"


class ReplayInstrumentStatus(StrEnum):
    """Per-instrument replay execution state."""

    EVALUATED = "EVALUATED"
    BLOCKED_MISSING_HISTORY = "BLOCKED_MISSING_HISTORY"
    BLOCKED_MISSING_AS_OF_SESSION = "BLOCKED_MISSING_AS_OF_SESSION"
    BLOCKED_MISSING_SYMBOL = "BLOCKED_MISSING_SYMBOL"
    BLOCKED_QUALITY = "BLOCKED_QUALITY"
    BLOCKED_DATASET_MISMATCH = "BLOCKED_DATASET_MISMATCH"


@dataclass(frozen=True, slots=True)
class SnapshotField:
    """One immutable current-value field attached to a scan candidate."""

    name: str
    value: SnapshotScalar

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("snapshot field name must be non-empty")


@dataclass(frozen=True, slots=True)
class StructuralLevel:
    """One structural level emitted by the shared pattern/event implementation."""

    name: str
    value: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("structural level name must be non-empty")
        if self.value <= 0:
            raise ValueError("structural level value must be positive")


@dataclass(frozen=True, slots=True)
class ScanStrategyDefinition:
    """Immutable strategy identity consumed by replay and later production scanning."""

    strategy_family_id: str
    strategy_version: str
    dataset_version: str
    feature_set_version: str
    evidence_profile_id: str
    evidence_package_checksum: str
    code_version: str
    config_schema_version: str
    eligibility_decision: ResearchDecision | None
    risk_policy_id: str | None = None
    rank_model_version: str | None = None
    strategy_contract_version: str = "scan-strategy-definition-v0.1"

    def __post_init__(self) -> None:
        required = (
            self.strategy_family_id,
            self.strategy_version,
            self.dataset_version,
            self.feature_set_version,
            self.evidence_profile_id,
            self.evidence_package_checksum,
            self.code_version,
            self.config_schema_version,
            self.strategy_contract_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("scan strategy required identifiers must be non-empty")
        optional = (self.risk_policy_id, self.rank_model_version)
        if any(value is not None and not value.strip() for value in optional):
            raise ValueError("optional scan strategy identifiers must be non-empty when supplied")

    @property
    def production_eligible(self) -> bool:
        """Return whether an explicit production-eligibility decision covers this strategy."""

        decision = self.eligibility_decision
        return (
            decision is not None
            and decision.subject_id == self.strategy_version
            and decision.state is ResearchDecisionState.PRODUCTION_ELIGIBLE
        )


@dataclass(frozen=True, slots=True)
class ReplayObservation:
    """Point-in-time state returned by a shared research implementation for one instrument."""

    source_date: date
    pattern_instance_id: str
    candidate_state: ScanCandidateState
    feature_snapshot: tuple[SnapshotField, ...]
    structural_levels: tuple[StructuralLevel, ...]
    quality_status: QualityStatus
    event_id: str | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.pattern_instance_id.strip():
            raise ValueError("replay observation pattern_instance_id must be non-empty")
        if self.event_id is not None and not self.event_id.strip():
            raise ValueError("replay observation event_id must be non-empty when supplied")
        names = tuple(item.name for item in self.feature_snapshot)
        if len(names) != len(set(names)):
            raise ValueError("replay observation feature names must be unique")
        levels = tuple(item.name for item in self.structural_levels)
        if len(levels) != len(set(levels)):
            raise ValueError("replay observation structural level names must be unique")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("replay observation reasons must be non-empty")


@dataclass(frozen=True, slots=True)
class ScanCandidate:
    """Auditable candidate snapshot produced by one historical replay run."""

    candidate_id: str
    scan_run_id: str
    as_of_date: date
    instrument_id: InstrumentId
    ticker_display: str
    strategy_family_id: str
    strategy_version: str
    pattern_instance_id: str
    event_id: str | None
    candidate_state: ScanCandidateState
    current_feature_snapshot: tuple[SnapshotField, ...]
    structural_levels: tuple[StructuralLevel, ...]
    evidence_profile_id: str
    risk_policy_id: str | None
    rank_model_version: str | None
    rank_score: float | None
    rank_components: tuple[SnapshotField, ...]
    data_freshness: str
    quality_status: QualityStatus
    dataset_version: str
    replay_publication_class: ReplayPublicationClass
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.candidate_id,
            self.scan_run_id,
            self.ticker_display,
            self.strategy_family_id,
            self.strategy_version,
            self.pattern_instance_id,
            self.evidence_profile_id,
            self.data_freshness,
            self.dataset_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("scan candidate required identifiers must be non-empty")
        if self.rank_score is not None and self.rank_model_version is None:
            raise ValueError("rank_score requires rank_model_version")
        if self.rank_components and self.rank_model_version is None:
            raise ValueError("rank components require rank_model_version")


@dataclass(frozen=True, slots=True)
class ReplayInstrumentRecord:
    """Audit record distinguishing no candidate from a blocked instrument."""

    instrument_id: InstrumentId
    status: ReplayInstrumentStatus
    latest_available_date: date | None
    candidate_id: str | None
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValueError("replay instrument record detail must be non-empty")
        if self.status is ReplayInstrumentStatus.EVALUATED and self.latest_available_date is None:
            raise ValueError("evaluated replay instrument requires latest_available_date")
        if self.candidate_id is not None and self.status is not ReplayInstrumentStatus.EVALUATED:
            raise ValueError("blocked replay instrument cannot reference a candidate")


@dataclass(frozen=True, slots=True)
class CandidateStateCount:
    """Candidate count retained in canonical scanner-state order."""

    state: ScanCandidateState
    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("candidate state count must be non-negative")


@dataclass(frozen=True, slots=True)
class HistoricalReplayResult:
    """Immutable historical scanner replay output and reproducibility manifest."""

    scan_run_id: str
    mode: ScannerMode
    replay_publication_class: ReplayPublicationClass
    as_of_date: date
    dataset_version: str
    universe_version: str
    feature_set_version: str
    strategy_family_id: str
    strategy_version: str
    evidence_profile_id: str
    evidence_package_checksum: str
    risk_policy_id: str | None
    rank_model_version: str | None
    code_version: str
    config_schema_version: str
    eligible_instrument_ids: tuple[InstrumentId, ...]
    instrument_records: tuple[ReplayInstrumentRecord, ...]
    candidates: tuple[ScanCandidate, ...]
    candidate_state_counts: tuple[CandidateStateCount, ...]
    output_checksum: str
    warnings: tuple[str, ...]
    execution_duration_ms: int | None = None
    manifest_version: str = "historical-scanner-replay-manifest-v0.1"

    def __post_init__(self) -> None:
        if self.mode is not ScannerMode.REPLAY:
            raise ValueError("historical replay result mode must be REPLAY")
        required = (
            self.scan_run_id,
            self.dataset_version,
            self.universe_version,
            self.feature_set_version,
            self.strategy_family_id,
            self.strategy_version,
            self.evidence_profile_id,
            self.evidence_package_checksum,
            self.code_version,
            self.config_schema_version,
            self.output_checksum,
            self.manifest_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("historical replay manifest identifiers must be non-empty")
        if self.execution_duration_ms is not None and self.execution_duration_ms < 0:
            raise ValueError("execution_duration_ms must be non-negative when supplied")
        expected_states = tuple(ScanCandidateState)
        if tuple(item.state for item in self.candidate_state_counts) != expected_states:
            raise ValueError("candidate state counts must retain canonical state order")
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("historical replay candidate IDs must be unique")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("historical replay warnings must be non-empty")


def strategy_from_research_evidence(
    package: ResearchEvidencePackage,
    *,
    strategy_family_id: str,
    strategy_version: str,
    feature_set_version: str,
    risk_policy_id: str | None = None,
    rank_model_version: str | None = None,
) -> ScanStrategyDefinition:
    """Build scanner strategy provenance directly from the canonical research evidence package."""

    return ScanStrategyDefinition(
        strategy_family_id=strategy_family_id,
        strategy_version=strategy_version,
        dataset_version=package.dataset_version,
        feature_set_version=feature_set_version,
        evidence_profile_id=package.package_id,
        evidence_package_checksum=package.package_checksum,
        code_version=package.code_version,
        config_schema_version=package.config_schema_version,
        eligibility_decision=package.decision,
        risk_policy_id=risk_policy_id,
        rank_model_version=rank_model_version,
    )
