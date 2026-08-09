from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.acceptance_ledger import AcceptanceLedgerError, load_acceptance_ledger

_REPO_LEDGER = Path("configs/data_foundation_acceptance_v0.1.json")


def test_checked_in_acceptance_ledger_has_complete_criterion_coverage() -> None:
    ledger = load_acceptance_ledger(_REPO_LEDGER)

    assert ledger.assessment_version == "data-foundation-acceptance-v0.1"
    assert len(ledger.report.evidence) == len(DataFoundationCriterion)
    assert {item.criterion for item in ledger.report.evidence} == set(DataFoundationCriterion)


def test_checked_in_ledger_remains_conservative_while_live_gates_are_open() -> None:
    ledger = load_acceptance_ledger(_REPO_LEDGER)
    by_criterion = {item.criterion: item for item in ledger.report.evidence}

    assert ledger.report.phase_complete is False
    assert (
        by_criterion[DataFoundationCriterion.HISTORICAL_INGESTION].status
        is AcceptanceEvidenceStatus.PARTIAL
    )
    assert (
        by_criterion[DataFoundationCriterion.CROSS_PROVIDER_VALIDATION].status
        is AcceptanceEvidenceStatus.PARTIAL
    )
    assert (
        by_criterion[DataFoundationCriterion.STORAGE_BENCHMARK].status
        is AcceptanceEvidenceStatus.PARTIAL
    )


def test_invalid_status_fails_instead_of_becoming_pending(tmp_path) -> None:
    payload = json.loads(_REPO_LEDGER.read_text(encoding="utf-8"))
    payload["criteria"][0]["status"] = "MAYBE"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AcceptanceLedgerError, match="invalid status"):
        load_acceptance_ledger(path)


def test_missing_criterion_fails_ledger_validation(tmp_path) -> None:
    payload = json.loads(_REPO_LEDGER.read_text(encoding="utf-8"))
    payload["criteria"] = payload["criteria"][:-1]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AcceptanceLedgerError, match="missing"):
        load_acceptance_ledger(path)


def test_demonstrated_criterion_requires_artifact_evidence(tmp_path) -> None:
    payload = json.loads(_REPO_LEDGER.read_text(encoding="utf-8"))
    price_item = next(
        item
        for item in payload["criteria"]
        if item["criterion"] == DataFoundationCriterion.PRICE_REPRESENTATION.value
    )
    price_item["evidence"] = []
    path = tmp_path / "unsupported.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AcceptanceLedgerError, match="cite at least one artifact"):
        load_acceptance_ledger(path)
