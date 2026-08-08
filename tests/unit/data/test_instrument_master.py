from datetime import date

import pytest

from trade_scout.data.contracts import SecurityType
from trade_scout.data.instrument_master import (
    InstrumentIdentityConflictError,
    SymbolHistoryConflictError,
    derive_instrument_id,
    instrument_from_primary_provider,
    link_provider_identity,
    normalize_symbol_history,
    resolve_provider_identity,
    symbol_as_of,
)
from trade_scout.data.provider import ProviderInstrument, ProviderSymbolHistory


def _provider_instrument(
    *,
    provider_instrument_id: str = "asset-1",
    symbol: str = "AAA",
) -> ProviderInstrument:
    return ProviderInstrument(
        provider_id="primary",
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        name="Example Corp",
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        active=True,
        first_trade_date=date(2010, 1, 4),
        end_date=None,
        source_fields={},
    )


def test_internal_id_depends_on_provider_identity_not_ticker() -> None:
    first = derive_instrument_id("primary", "asset-1")
    second = instrument_from_primary_provider(_provider_instrument(symbol="RENAMED"))

    assert second.instrument_id == first


def test_ticker_reuse_does_not_merge_distinct_provider_ids() -> None:
    first = instrument_from_primary_provider(_provider_instrument(provider_instrument_id="asset-1"))
    second = instrument_from_primary_provider(_provider_instrument(provider_instrument_id="asset-2"))

    assert first.primary_symbol == second.primary_symbol
    assert first.instrument_id != second.instrument_id


def test_secondary_provider_link_is_explicit_and_preserves_internal_id() -> None:
    instrument = instrument_from_primary_provider(_provider_instrument())

    linked = link_provider_identity(
        instrument,
        provider_id="secondary",
        provider_instrument_id="sec-999",
    )

    assert linked.instrument_id == instrument.instrument_id
    assert linked.provider_ids["secondary"] == "sec-999"
    assert "secondary" not in instrument.provider_ids
    assert (
        resolve_provider_identity(
            [linked], provider_id="secondary", provider_instrument_id="sec-999"
        )
        == instrument.instrument_id
    )


def test_conflicting_provider_link_fails() -> None:
    instrument = link_provider_identity(
        instrument_from_primary_provider(_provider_instrument()),
        provider_id="secondary",
        provider_instrument_id="sec-1",
    )

    with pytest.raises(InstrumentIdentityConflictError):
        link_provider_identity(
            instrument,
            provider_id="secondary",
            provider_instrument_id="sec-2",
        )


def test_symbol_history_resolves_point_in_time() -> None:
    instrument = instrument_from_primary_provider(_provider_instrument())
    result = normalize_symbol_history(
        [
            ProviderSymbolHistory(
                provider_id="primary",
                provider_instrument_id="asset-1",
                symbol="OLD",
                exchange="XNYS",
                effective_from=date(2010, 1, 4),
                effective_to=date(2020, 6, 30),
            ),
            ProviderSymbolHistory(
                provider_id="primary",
                provider_instrument_id="asset-1",
                symbol="NEW",
                exchange="XNYS",
                effective_from=date(2020, 7, 1),
                effective_to=None,
            ),
        ],
        [instrument],
    )

    before = symbol_as_of(result.records, instrument_id=instrument.instrument_id, as_of=date(2020, 6, 1))
    after = symbol_as_of(result.records, instrument_id=instrument.instrument_id, as_of=date(2020, 7, 1))

    assert before is not None and before.symbol == "OLD"
    assert after is not None and after.symbol == "NEW"
    assert result.unresolved == ()


def test_unresolved_symbol_history_is_not_guessed_from_matching_ticker() -> None:
    instrument = instrument_from_primary_provider(_provider_instrument(symbol="AAA"))
    result = normalize_symbol_history(
        [
            ProviderSymbolHistory(
                provider_id="primary",
                provider_instrument_id="different-asset",
                symbol="AAA",
                exchange="XNYS",
                effective_from=date(2015, 1, 1),
                effective_to=None,
            )
        ],
        [instrument],
    )

    assert result.records == ()
    assert len(result.unresolved) == 1


def test_overlapping_symbol_history_fails() -> None:
    instrument = instrument_from_primary_provider(_provider_instrument())

    with pytest.raises(SymbolHistoryConflictError):
        normalize_symbol_history(
            [
                ProviderSymbolHistory(
                    provider_id="primary",
                    provider_instrument_id="asset-1",
                    symbol="AAA",
                    exchange="XNYS",
                    effective_from=date(2010, 1, 1),
                    effective_to=date(2020, 12, 31),
                ),
                ProviderSymbolHistory(
                    provider_id="primary",
                    provider_instrument_id="asset-1",
                    symbol="BBB",
                    exchange="XNYS",
                    effective_from=date(2020, 12, 31),
                    effective_to=None,
                ),
            ],
            [instrument],
        )
