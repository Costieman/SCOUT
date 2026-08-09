"""Provider-specific acceptance gate for the Phase 1 canonical market-data source."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ProviderAcceptanceCriterion(StrEnum):
    """Evidence families required before a provider may become canonical."""

    LICENSE_AND_RETENTION = "license_and_retention_rights"
    REPRODUCIBLE_HISTORICAL_BACKFILL = "reproducible_historical_backfill"
    RAW_PRESERVATION = "immutable_raw_preservation"
    IDENTIFIER_AND_SYMBOL_MAPPING = "identifier_and_symbol_mapping"
    CORPORATE_ACTION_HANDLING = "corporate_action_handling"
    DELISTING_COVERAGE = "delisting_coverage_characterized"
    RATE_RETRY_CHECKPOINT = "rate_retry_checkpoint_behavior"
    CANONICAL_NORMALIZATION_QUALITY = "canonical_normalization_and_quality"
    SECONDARY_VALIDATION = "secondary_provider_validation"
    IDEMPOTENT_DAILY_UPDATE = "idempotent_deterministic_daily_update"
    DOWNSTREAM_VENDOR_INDEPENDENCE = "downstream_vendor_independence"
    KNOWN_LIMITATIONS = "known_limitations_documented"
    REPRESENTATIVE_CANONICAL_SAMPLE = "representative_canonical_sample"


class ProviderEvidenceStatus(StrEnum):
    """Conservative status for one provider-acceptance criterion."""

    NOT_DEMONSTRATED = "NOT_DEMONSTRATED"
    PARTIAL = "PARTIAL"
    DEMONSTRATED = "DEMONSTRATED"


@dataclass(frozen=True, slots=True)
class ProviderAcceptanceEvidence:
    """Auditable evidence for one provider-specific acceptance criterion."""

    criterion: ProviderAcceptanceCriterion
    status: ProviderEvidenceStatus
    evidence: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        if not self.note.strip():
            raise ValueError("provider acceptance evidence note must be non-empty")
        if self.status is ProviderEvidenceStatus.DEMONSTRATED and not self.evidence:
            raise ValueError("demonstrated provider criterion requires evidence references")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("provider acceptance evidence references must be non-empty")
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("provider acceptance evidence references must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ProviderAcceptanceReport:
    """Complete provider-specific gate report; acceptance requires every criterion."""

    provider_id: str
    assessment_version: str
    evidence: tuple[ProviderAcceptanceEvidence, ...]

    @property
    def accepted(self) -> bool:
        """Return true only when every required criterion is demonstrated."""

        return all(item.status is ProviderEvidenceStatus.DEMONSTRATED for item in self.evidence)

    @property
    def unresolved(self) -> tuple[ProviderAcceptanceEvidence, ...]:
        """Return criteria that still block canonical-provider acceptance."""

        return tuple(
            item for item in self.evidence if item.status is not ProviderEvidenceStatus.DEMONSTRATED
        )


class ProviderAcceptanceError(ValueError):
    """Raised when a provider acceptance assessment is malformed or incomplete."""


def evaluate_provider_acceptance(
    provider_id: str,
    assessment_version: str,
    evidence: tuple[ProviderAcceptanceEvidence, ...],
) -> ProviderAcceptanceReport:
    """Require one and only one explicit evidence record for every acceptance criterion."""

    if not provider_id.strip():
        raise ProviderAcceptanceError("provider_id must be non-empty")
    if not assessment_version.strip():
        raise ProviderAcceptanceError("assessment_version must be non-empty")

    by_criterion: dict[ProviderAcceptanceCriterion, ProviderAcceptanceEvidence] = {}
    for item in evidence:
        if item.criterion in by_criterion:
            raise ProviderAcceptanceError(
                f"duplicate provider acceptance criterion: {item.criterion.value}"
            )
        by_criterion[item.criterion] = item

    missing = set(ProviderAcceptanceCriterion) - set(by_criterion)
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ProviderAcceptanceError(f"provider acceptance assessment is missing: {names}")

    ordered = tuple(by_criterion[criterion] for criterion in ProviderAcceptanceCriterion)
    return ProviderAcceptanceReport(
        provider_id=provider_id.strip(),
        assessment_version=assessment_version.strip(),
        evidence=ordered,
    )


def load_provider_acceptance(path: Path) -> ProviderAcceptanceReport:
    """Load a checked-in provider assessment without inferring omitted or optimistic evidence."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProviderAcceptanceError(
            f"cannot read provider acceptance assessment: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderAcceptanceError("provider acceptance assessment is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderAcceptanceError("provider acceptance assessment root must be an object")

    provider_id = payload.get("provider_id")
    assessment_version = payload.get("assessment_version")
    raw_criteria = payload.get("criteria")
    if not isinstance(provider_id, str) or not isinstance(assessment_version, str):
        raise ProviderAcceptanceError("provider_id and assessment_version must be strings")
    if not isinstance(raw_criteria, list):
        raise ProviderAcceptanceError("provider acceptance criteria must be an array")

    evidence = tuple(_evidence_from_payload(item) for item in raw_criteria)
    return evaluate_provider_acceptance(provider_id, assessment_version, evidence)


def _evidence_from_payload(payload: object) -> ProviderAcceptanceEvidence:
    if not isinstance(payload, dict):
        raise ProviderAcceptanceError("provider acceptance criterion must be an object")
    try:
        criterion = ProviderAcceptanceCriterion(str(payload["criterion"]))
        status = ProviderEvidenceStatus(str(payload["status"]))
    except (KeyError, ValueError) as exc:
        raise ProviderAcceptanceError("provider acceptance criterion/status is invalid") from exc
    raw_evidence = payload.get("evidence")
    note = payload.get("note")
    if not isinstance(raw_evidence, list) or not all(
        isinstance(item, str) for item in raw_evidence
    ):
        raise ProviderAcceptanceError("provider acceptance evidence must be a string array")
    if not isinstance(note, str):
        raise ProviderAcceptanceError("provider acceptance note must be text")
    return ProviderAcceptanceEvidence(
        criterion=criterion,
        status=status,
        evidence=tuple(raw_evidence),
        note=note,
    )
