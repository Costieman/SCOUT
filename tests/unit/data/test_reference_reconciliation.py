from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import SecurityType
from trade_scout.data.provider import ProviderInstrument
from trade_scout.data.reference_reconciliation import (
    HistoricalReferenceBackProjectionError,
    ReferenceCandidateState,
    reconcile_current_reference_candidates,
)


def _instrument(
    *,
    provider_id: str,
    provider_instrument_id: str,
    symbol: str,
    exchange: str,
    name: str,
) -> ProviderInstrument:
    return ProviderInstrument(
        provider_id=provider_id,
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        name=name,
        exchange=exchange,
        security_type=SecurityType.OTHER,
        currency="USD",
        active=True,
        first_trade_date=None,
        end_date=None,
        source_fields={},
    )


def test_exact_current_symbol_exchange_yields_review_candidate_not_identity_link() -> None:
    market = _instrument(
        provider_id="alpha_vantage",
        provider_instrument_id="AAPL",
        symbol="AAPL",
        exchange="NASDAQ",
        name="Apple Inc",
    )
    reference = _instrument(
        provider_id="sec_edgar",
        provider_instrument_id="sec_edgar:cik:320193:ticker:AAPL",
        symbol="AAPL",
        exchange="Nasdaq",
        name="Apple Inc.",
    )

    candidates = reconcile_current_reference_candidates((market,), (reference,))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.state is ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE
    assert candidate.has_unique_candidate is True
    assert candidate.market_provider_instrument_id == "AAPL"
    assert candidate.reference_provider_instrument_ids == (
        "sec_edgar:cik:320193:ticker:AAPL",
    )
    assert any("non-authoritative" in item for item in candidate.evidence)


def test_blank_market_name_does_not_prevent_current_reference_candidate() -> None:
    market = _instrument(
        provider_id="alpha_vantage",
        provider_instrument_id="ARGD",
        symbol="ARGD",
        exchange="NYSE",
        name="",
    )
    reference = _instrument(
        provider_id="sec_edgar",
        provider_instrument_id="sec_edgar:cik:1:ticker:ARGD",
        symbol="ARGD",
        exchange="NYSE",
        name="Reference issuer name",
    )

    candidate = reconcile_current_reference_candidates((market,), (reference,))[0]

    assert candidate.state is ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE
    assert "name unavailable on at least one source" in candidate.evidence


def test_exchange_disagreement_is_retained_as_weaker_symbol_only_evidence() -> None:
    market = _instrument(
        provider_id="primary",
        provider_instrument_id="ABC",
        symbol="ABC",
        exchange="NYSE",
        name="ABC Corp",
    )
    reference = _instrument(
        provider_id="reference",
        provider_instrument_id="ref-abc",
        symbol="ABC",
        exchange="NASDAQ",
        name="ABC Corp",
    )

    candidate = reconcile_current_reference_candidates((market,), (reference,))[0]

    assert candidate.state is ReferenceCandidateState.SYMBOL_ONLY
    assert candidate.has_unique_candidate is True
    assert "exchange does not agree" in candidate.evidence


def test_multiple_reference_rows_remain_ambiguous() -> None:
    market = _instrument(
        provider_id="primary",
        provider_instrument_id="ABC",
        symbol="ABC",
        exchange="NYSE",
        name="ABC Corp",
    )
    references = (
        _instrument(
            provider_id="reference",
            provider_instrument_id="ref-1",
            symbol="ABC",
            exchange="NYSE",
            name="ABC Corp",
        ),
        _instrument(
            provider_id="reference",
            provider_instrument_id="ref-2",
            symbol="ABC",
            exchange="NYSE",
            name="ABC Holdings",
        ),
    )

    candidate = reconcile_current_reference_candidates((market,), references)[0]

    assert candidate.state is ReferenceCandidateState.AMBIGUOUS
    assert candidate.has_unique_candidate is False
    assert candidate.reference_provider_instrument_ids == ("ref-1", "ref-2")


def test_symbol_punctuation_is_not_rewritten_for_convenient_matching() -> None:
    market = _instrument(
        provider_id="primary",
        provider_instrument_id="BRK.B",
        symbol="BRK.B",
        exchange="NYSE",
        name="Berkshire Hathaway",
    )
    reference = _instrument(
        provider_id="reference",
        provider_instrument_id="BRK-B",
        symbol="BRK-B",
        exchange="NYSE",
        name="Berkshire Hathaway",
    )

    candidate = reconcile_current_reference_candidates((market,), (reference,))[0]

    assert candidate.state is ReferenceCandidateState.UNMATCHED
    assert candidate.reference_provider_instrument_ids == ()


def test_historical_snapshot_reconciliation_is_rejected() -> None:
    with pytest.raises(HistoricalReferenceBackProjectionError, match="historical market snapshot"):
        reconcile_current_reference_candidates((), (), market_as_of=date(2021, 10, 1))
