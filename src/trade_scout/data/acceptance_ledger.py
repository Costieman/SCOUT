"""Versioned file-backed evidence ledger for the Phase 1 data-foundation exit gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.acceptance import (
    AcceptanceEvidence,
    AcceptanceEvidenceStatus,
    DataFoundationAcceptanceReport,
    DataFoundationCriterion,
    evaluate_data_foundation_acceptance,
)


@dataclass(frozen=True, slots=True)
class AcceptanceLedger:
    """One versioned acceptance assessment plus its validated gate report."""

    assessment_version: str
    report: DataFoundationAcceptanceReport


class AcceptanceLedgerError(ValueError):
    """Raised when a checked-in acceptance ledger is malformed or incomplete."""


def load_acceptance_ledger(path: Path) -> AcceptanceLedger:
    """Parse and validate a JSON acceptance ledger without inferring missing evidence."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AcceptanceLedgerError(f"cannot read acceptance ledger: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AcceptanceLedgerError(f"acceptance ledger is invalid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise AcceptanceLedgerError("acceptance ledger root must be a JSON object")
    version = payload.get("assessment_version")
    if not isinstance(version, str) or not version.strip():
        raise AcceptanceLedgerError("acceptance ledger requires a non-empty assessment_version")
    raw_criteria = payload.get("criteria")
    if not isinstance(raw_criteria, list):
        raise AcceptanceLedgerError("acceptance ledger criteria must be a JSON array")

    evidence = tuple(_evidence_from_payload(item) for item in raw_criteria)
    try:
        report = evaluate_data_foundation_acceptance(evidence)
    except ValueError as exc:
        raise AcceptanceLedgerError(str(exc)) from exc
    return AcceptanceLedger(assessment_version=version.strip(), report=report)


def _evidence_from_payload(payload: object) -> AcceptanceEvidence:
    if not isinstance(payload, dict):
        raise AcceptanceLedgerError("each acceptance criterion must be a JSON object")
    try:
        criterion = DataFoundationCriterion(str(payload["criterion"]))
    except (KeyError, ValueError) as exc:
        raise AcceptanceLedgerError("acceptance criterion identifier is invalid") from exc
    try:
        status = AcceptanceEvidenceStatus(str(payload["status"]))
    except (KeyError, ValueError) as exc:
        raise AcceptanceLedgerError(f"invalid status for {criterion.value}") from exc

    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not all(isinstance(item, str) for item in raw_evidence):
        raise AcceptanceLedgerError(f"evidence for {criterion.value} must be a string array")
    note = payload.get("note")
    if not isinstance(note, str):
        raise AcceptanceLedgerError(f"note for {criterion.value} must be text")
    try:
        return AcceptanceEvidence(
            criterion=criterion,
            status=status,
            evidence=tuple(raw_evidence),
            note=note,
        )
    except ValueError as exc:
        raise AcceptanceLedgerError(str(exc)) from exc
