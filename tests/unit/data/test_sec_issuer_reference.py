from __future__ import annotations

from trade_scout.data.contracts import SecurityType
from trade_scout.data.instrument_master import instrument_from_primary_provider, link_provider_identity
from trade_scout.data.provider import ProviderInstrument
from trade_scout.data.sec_issuer_reference import project_reviewed_sec_issuer_references


def _market() -> ProviderInstrument:
    return ProviderInstrument(
        provider_id="alpha_vantage",
        provider_instrument_id="alpha_vantage:symbol:AAPL",
        symbol="AAPL",
        name="Apple Inc",
        exchange="NASDAQ",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        active=True,
        first_trade_date=None,
        end_date=None,
        source_fields={},
    )


def _sec() -> ProviderInstrument:
    return ProviderInstrument(
        provider_id="sec_edgar",
        provider_instrument_id="sec_edgar:cik:320193:ticker:AAPL",
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        security_type=SecurityType.OTHER,
        currency="USD",
        active=True,
        first_trade_date=None,
        end_date=None,
        source_fields={"cik": 320193},
    )


def test_sec_issuer_metadata_projects_only_through_existing_reviewed_link() -> None:
    canonical = instrument_from_primary_provider(_market())
    linked = link_provider_identity(
        canonical,
        provider_id="sec_edgar",
        provider_instrument_id="sec_edgar:cik:320193:ticker:AAPL",
    )

    result = project_reviewed_sec_issuer_references((linked,), (_sec(),))

    assert len(result.resolved) == 1
    assert result.resolved[0].instrument_id == canonical.instrument_id
    assert result.resolved[0].cik == 320193
    assert result.unresolved == ()
    assert linked.instrument_id == canonical.instrument_id


def test_unreviewed_ticker_match_stays_unresolved() -> None:
    canonical = instrument_from_primary_provider(_market())

    result = project_reviewed_sec_issuer_references((canonical,), (_sec(),))

    assert result.resolved == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].reason == "no reviewed canonical SEC provider link"


def test_cik_is_not_used_as_security_identity() -> None:
    canonical = instrument_from_primary_provider(_market())
    sec = _sec()

    result = project_reviewed_sec_issuer_references((canonical,), (sec,))

    assert result.unresolved[0].cik == 320193
    assert canonical.instrument_id != "320193"
