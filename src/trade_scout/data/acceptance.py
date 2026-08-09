"""Explicit Phase 1 data-foundation acceptance gate.

The data specification defines completion as demonstrated evidence, not code volume. This module
keeps that boundary machine-readable so later phases cannot treat partial implementation as a
completed historical-data foundation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class DataFoundationCriterion(StrEnum):
    """Acceptance criteria defined by the data architecture specification."""

    INSTRUMENT_MASTER = "stable_instrument_master_and_symbol_history"
    HISTORICAL_INGESTION = "reproducible_historical_ohlcv_ingestion"
    PRICE_REPRESENTATION = "explicit_raw_vs_adjusted_price_handling"
    DELISTINGS = "historical_delisting_support"
    POINT_IN_TIME_UNIVERSE = "point_in_time_universe_construction"
    DATA_QUALITY = "automated_quality_and_quarantine"
    CROSS_PROVIDER_VALIDATION = "cross_provider_validation"
    VERSIONING_PROVENANCE = "immutable_dataset_versioning_and_provenance"
    STORAGE_BENCHMARK = "representative_parquet_duckdb_benchmark"
    DOWNSTREAM_CONTRACT = "downstream_research_data_contract_consumption"
    INCREMENTAL_UPDATE = "deterministic_incremental_update_workflow"


class AcceptanceEvidenceStatus(StrEnum):
    """State of one criterion's evidence without weakening a failed or missing prerequisite."""

    DEMONSTRATED = "DEMONSTRATED"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class AcceptanceEvidence:
    """Auditable evidence attached to one Phase 1 acceptance criterion."""

    criterion: DataFoundationCriterion
    status: AcceptanceEvidenceStatus
    evidence: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        if not self.note.strip():
            raise ValueError("acceptance evidence note must be non-empty")
        if self.status is AcceptanceEvidenceStatus.DEMONSTRATED and not self.evidence:
            raise ValueError("demonstrated acceptance evidence must cite at least one artifact")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("acceptance evidence artifact references must be non-empty")


@dataclass(frozen=True, slots=True)
class DataFoundationAcceptanceReport:
    """Complete criterion-by-criterion Phase 1 gate evaluation."""

    evidence: tuple[AcceptanceEvidence, ...]

    @property
    def phase_complete(self) -> bool:
        """Return true only when every criterion has demonstrated evidence."""

        return all(item.status is AcceptanceEvidenceStatus.DEMONSTRATED for item in self.evidence)

    @property
    def unresolved(self) -> tuple[AcceptanceEvidence, ...]:
        """Return criteria that still prevent the Phase 1 exit gate from closing."""

        return tuple(
            item
            for item in self.evidence
            if item.status is not AcceptanceEvidenceStatus.DEMONSTRATED
        )

    def require_complete(self) -> None:
        """Raise when any criterion remains incomplete, preserving visible failure semantics."""

        if self.phase_complete:
            return
        pending = ", ".join(item.criterion.value for item in self.unresolved)
        raise DataFoundationIncompleteError(f"Phase 1 data foundation is incomplete: {pending}")


class DataFoundationIncompleteError(RuntimeError):
    """Raised when a downstream phase attempts to cross an incomplete Phase 1 gate."""


def evaluate_data_foundation_acceptance(
    evidence: Iterable[AcceptanceEvidence],
) -> DataFoundationAcceptanceReport:
    """Validate complete criterion coverage and return an immutable acceptance report.

    Exactly one evidence record is required for every criterion. Missing criteria and duplicate
    records are errors rather than implicit failures because an incomplete checklist is itself an
    invalid acceptance assessment.
    """

    records = tuple(evidence)
    by_criterion: dict[DataFoundationCriterion, AcceptanceEvidence] = {}
    for item in records:
        if item.criterion in by_criterion:
            raise ValueError(f"duplicate acceptance evidence for {item.criterion.value}")
        by_criterion[item.criterion] = item

    required = set(DataFoundationCriterion)
    supplied = set(by_criterion)
    missing = required - supplied
    if missing:
        details = ",".join(sorted(item.value for item in missing))
        raise ValueError(f"invalid Phase 1 acceptance coverage: missing={details}")

    ordered = tuple(by_criterion[item] for item in DataFoundationCriterion)
    return DataFoundationAcceptanceReport(evidence=ordered)
