from trade_scout.data.free_stack_identity import (
    FreeStackIdentityState,
    StooqIdentityClaim,
    reconcile_stooq_claim_with_sec,
)
from trade_scout.data.providers.sec_edgar import SecTickerAssociation


def _claim() -> StooqIdentityClaim:
    return StooqIdentityClaim(
        query_symbol="AAPL.US",
        provider_instrument_id="reviewed:aapl",
        ticker="AAPL",
        exchange="Nasdaq",
    )


def test_unique_exact_sec_match_is_issuer_reference_only() -> None:
    evidence = reconcile_stooq_claim_with_sec(
        _claim(),
        (
            SecTickerAssociation(
                cik=320193,
                name="Apple Inc.",
                ticker="AAPL",
                exchange="Nasdaq",
            ),
        ),
    )

    assert evidence.state is FreeStackIdentityState.UNIQUE_ISSUER_REFERENCE
    assert evidence.sec_ciks == (320193,)
    assert "not a permanent security ID" in evidence.note


def test_exchange_mismatch_does_not_fall_back_to_ticker() -> None:
    evidence = reconcile_stooq_claim_with_sec(
        _claim(),
        (
            SecTickerAssociation(
                cik=320193,
                name="Apple Inc.",
                ticker="AAPL",
                exchange="NYSE",
            ),
        ),
    )

    assert evidence.state is FreeStackIdentityState.NO_SEC_MATCH
    assert evidence.sec_ciks == ()


def test_multiple_exact_ciks_remain_ambiguous() -> None:
    evidence = reconcile_stooq_claim_with_sec(
        _claim(),
        (
            SecTickerAssociation(320193, "Apple Inc.", "AAPL", "Nasdaq"),
            SecTickerAssociation(999999, "Other Issuer", "AAPL", "Nasdaq"),
        ),
    )

    assert evidence.state is FreeStackIdentityState.AMBIGUOUS_SEC_MATCH
    assert evidence.sec_ciks == (320193, 999999)


def test_company_name_is_not_used_as_fallback_identity() -> None:
    evidence = reconcile_stooq_claim_with_sec(
        _claim(),
        (
            SecTickerAssociation(320193, "Apple Inc.", "APC", "Nasdaq"),
        ),
    )

    assert evidence.state is FreeStackIdentityState.NO_SEC_MATCH
