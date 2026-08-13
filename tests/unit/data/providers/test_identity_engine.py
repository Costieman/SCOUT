from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.auto_identity_import import (
    AutoIdentityEvidence,
    AutoIdentityImportError,
    SecIdentityClient,
    build_auto_reviewed_candidate,
    candidate_dataset_version,
)
from trade_scout.data.reviewed_identity_snapshot import ReviewedIdentitySnapshotCandidate


def _empty_candidate() -> ReviewedIdentitySnapshotCandidate:
    return ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version="test-reviewed-v0.1",
        primary_provider_id="trade_scout_review",
        identity_definition_version="reviewed-permanent-identity-v0.1",
        symbol_history_definition_version="explicit-dated-symbol-history-v0.1",
        identity_seed_sha256="0" * 64,
        lineage_audit_sha256="1" * 64,
        instruments=(),
        symbol_history=(),
        provider_series_links=(),
        coverage_gaps=(),
        evidence_refs=(),
    )


def test_sec_client_requires_contact_email() -> None:
    with pytest.raises(ValueError, match="contact email"):
        SecIdentityClient(user_agent="Trade Scout Research")


def test_candidate_materialization_rejects_deferred_evidence() -> None:
    evidence = AutoIdentityEvidence(
        source_symbol="TEST",
        observed_first_date=date(2000, 1, 3),
        cik=1,
        company_name="Test Corp",
        exchange="Nasdaq",
        source_url=None,
        source_title=None,
        evidence_kind="BOUNDARY_NOT_PROVEN",
        ready=False,
        reason="not proven",
    )
    with pytest.raises(AutoIdentityImportError, match="non-ready evidence"):
        build_auto_reviewed_candidate(existing=_empty_candidate(), ready_evidence=(evidence,))


def test_candidate_dataset_version_is_deterministic() -> None:
    candidate = _empty_candidate()
    first = candidate_dataset_version(candidate)
    second = candidate_dataset_version(candidate)
    assert first == second
    assert first.startswith("tiingo-reviewed-split-only-auto-")
