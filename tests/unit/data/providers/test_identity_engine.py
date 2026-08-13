from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.identity_adjudication import (
    IdentityAdjudicationError,
    IdentityDecisionState,
    IdentityEvidence,
    IdentityEvidenceState,
    IdentityReviewInput,
    adjudicate_identity_case,
    build_identity_batch_report,
)
from trade_scout.data.providers.sec_identity import (
    SecCompany,
    collect_sec_identity_evidence,
)


_CAMPAIGN_START = date(1996, 1, 2)


def _review(*, first: date = date(2020, 1, 2), anomalies: int = 0) -> IdentityReviewInput:
    return IdentityReviewInput(
        source_symbol="TEST",
        observed_first_date=first,
        observed_last_date=date(2026, 8, 7),
        row_count=1000,
        structural_anomaly_count=anomalies,
    )


def _evidence(
    state: IdentityEvidenceState,
    *,
    effective: date | None,
) -> IdentityEvidence:
    supporting = state in {
        IdentityEvidenceState.EXACT_PUBLIC_TRADING_START,
        IdentityEvidenceState.CAMPAIGN_CONTINUITY,
    }
    return IdentityEvidence(
        source_symbol="TEST",
        state=state,
        source_url="https://www.sec.gov/example" if supporting else None,
        source_title="SEC 10-K" if supporting else None,
        effective_date=effective,
        regulator_id="CIK0000000001" if supporting else None,
        company_name="Test Corp" if supporting else None,
        exchange="Nasdaq" if supporting else None,
        detail="synthetic evidence",
    )


def test_exact_public_start_can_become_ready() -> None:
    decision = adjudicate_identity_case(
        _review(),
        _evidence(IdentityEvidenceState.EXACT_PUBLIC_TRADING_START, effective=date(2020, 1, 2)),
        campaign_start=_CAMPAIGN_START,
    )

    assert decision.state is IdentityDecisionState.READY_FOR_REVIEW


def test_exact_public_start_mismatch_defers() -> None:
    decision = adjudicate_identity_case(
        _review(),
        _evidence(IdentityEvidenceState.EXACT_PUBLIC_TRADING_START, effective=date(2019, 12, 31)),
        campaign_start=_CAMPAIGN_START,
    )

    assert decision.state is IdentityDecisionState.DEFERRED
    assert "does not equal" in decision.reason


def test_campaign_continuity_only_applies_at_campaign_start() -> None:
    ready = adjudicate_identity_case(
        _review(first=_CAMPAIGN_START),
        _evidence(IdentityEvidenceState.CAMPAIGN_CONTINUITY, effective=_CAMPAIGN_START),
        campaign_start=_CAMPAIGN_START,
    )
    deferred = adjudicate_identity_case(
        _review(first=date(1996, 2, 1)),
        _evidence(IdentityEvidenceState.CAMPAIGN_CONTINUITY, effective=_CAMPAIGN_START),
        campaign_start=_CAMPAIGN_START,
    )

    assert ready.state is IdentityDecisionState.READY_FOR_REVIEW
    assert deferred.state is IdentityDecisionState.DEFERRED


def test_structural_anomaly_always_defers() -> None:
    decision = adjudicate_identity_case(
        _review(anomalies=1),
        _evidence(IdentityEvidenceState.EXACT_PUBLIC_TRADING_START, effective=date(2020, 1, 2)),
        campaign_start=_CAMPAIGN_START,
    )

    assert decision.state is IdentityDecisionState.DEFERRED
    assert "structural" in decision.reason


def test_batch_rejects_duplicate_symbols() -> None:
    case = (
        _review(),
        _evidence(IdentityEvidenceState.EXACT_PUBLIC_TRADING_START, effective=date(2020, 1, 2)),
    )
    with pytest.raises(IdentityAdjudicationError, match="duplicate"):
        build_identity_batch_report((case, case), campaign_start=_CAMPAIGN_START)


class _FakeSecClient:
    def __init__(self, filing_text: str) -> None:
        self.filing_text = filing_text

    def get_json(self, url: str) -> object:
        if "submissions/CIK" in url:
            return {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000000001-20-000001"],
                        "filingDate": ["2020-03-01"],
                        "form": ["10-K"],
                        "primaryDocument": ["test10k.htm"],
                    },
                    "files": [],
                }
            }
        raise AssertionError(f"unexpected URL {url}")

    def get_text(self, url: str) -> str:
        assert "Archives/edgar/data" in url
        return self.filing_text


def test_sec_exact_start_requires_date_ticker_and_trading_language() -> None:
    client = _FakeSecClient(
        "<html>Our common stock began trading on Nasdaq under the symbol TEST on January 2, 2020.</html>"
    )
    evidence = collect_sec_identity_evidence(
        client=client,  # type: ignore[arg-type]
        catalog={"TEST": SecCompany(cik=1, name="Test Corp", ticker="TEST", exchange="Nasdaq")},
        source_symbol="TEST",
        observed_first_date=date(2020, 1, 2),
        campaign_start=_CAMPAIGN_START,
    )

    assert evidence.state is IdentityEvidenceState.EXACT_PUBLIC_TRADING_START
    assert evidence.effective_date == date(2020, 1, 2)


def test_sec_campaign_continuity_requires_ticker_exchange_cooccurrence() -> None:
    client = _FakeSecClient(
        "<html>Test Corp common stock, symbol TEST, is listed on the New York Stock Exchange.</html>"
    )
    evidence = collect_sec_identity_evidence(
        client=client,  # type: ignore[arg-type]
        catalog={"TEST": SecCompany(cik=1, name="Test Corp", ticker="TEST", exchange="NYSE")},
        source_symbol="TEST",
        observed_first_date=_CAMPAIGN_START,
        campaign_start=_CAMPAIGN_START,
    )

    assert evidence.state is IdentityEvidenceState.CAMPAIGN_CONTINUITY


def test_sec_current_registrant_without_boundary_support_stays_insufficient() -> None:
    client = _FakeSecClient("<html>Test Corp annual report.</html>")
    evidence = collect_sec_identity_evidence(
        client=client,  # type: ignore[arg-type]
        catalog={"TEST": SecCompany(cik=1, name="Test Corp", ticker="TEST", exchange="Nasdaq")},
        source_symbol="TEST",
        observed_first_date=date(2020, 1, 2),
        campaign_start=_CAMPAIGN_START,
    )

    assert evidence.state is IdentityEvidenceState.CURRENT_REGISTRANT_ONLY
