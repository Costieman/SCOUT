from __future__ import annotations

from trade_scout.data.contracts import SecurityType
from trade_scout.data.provider import ProviderInstrument
from trade_scout.data.providers.eodhd_representative_sample import (
    EodhdRepresentativeSampleError,
    EodhdRepresentativeSamplePolicy,
    campaign_payload,
    select_eodhd_representative_sample,
)


def _instrument(
    index: int,
    *,
    active: bool,
    exchange: str = "NYSE",
    security_type: SecurityType = SecurityType.COMMON_STOCK,
    isin: bool = True,
) -> ProviderInstrument:
    provider_id = f"eodhd:isin:US{index:010d}" if isin else f"eodhd:symbol:S{index}.US"
    return ProviderInstrument(
        provider_id="eodhd",
        provider_instrument_id=provider_id,
        symbol=f"S{index}.US",
        name=f"Security {index}",
        exchange=exchange,
        security_type=security_type,
        currency="USD",
        active=active,
        first_trade_date=None,
        end_date=None,
        source_fields={},
    )


def test_selection_is_deterministic_and_enforces_composition() -> None:
    instruments = tuple(
        [_instrument(i, active=True, exchange="NYSE" if i % 2 else "NASDAQ") for i in range(20)]
        + [_instrument(100 + i, active=False, exchange="NYSE") for i in range(8)]
    )
    policy = EodhdRepresentativeSamplePolicy(active_count=10, delisted_count=4, min_exchanges=2)

    first = select_eodhd_representative_sample(instruments, policy=policy)
    second = select_eodhd_representative_sample(tuple(reversed(instruments)), policy=policy)

    assert [item.provider_instrument_id for item in first.instruments] == [
        item.provider_instrument_id for item in second.instruments
    ]
    assert len(first.active) == 10
    assert len(first.delisted) == 4
    assert set(first.exchanges) == {"NASDAQ", "NYSE"}


def test_selection_excludes_provisional_and_non_common_stock_identity() -> None:
    instruments = (
        _instrument(1, active=True, exchange="NYSE"),
        _instrument(2, active=True, exchange="NASDAQ"),
        _instrument(3, active=True, exchange="NYSE", isin=False),
        _instrument(4, active=True, exchange="NYSE", security_type=SecurityType.ETF),
        _instrument(5, active=False, exchange="NYSE"),
    )
    policy = EodhdRepresentativeSamplePolicy(active_count=2, delisted_count=1, min_exchanges=2)

    selection = select_eodhd_representative_sample(instruments, policy=policy)

    ids = {item.provider_instrument_id for item in selection.instruments}
    assert "eodhd:symbol:S3.US" not in ids
    assert all(item.security_type is SecurityType.COMMON_STOCK for item in selection.instruments)


def test_selection_fails_when_exchange_floor_cannot_be_met() -> None:
    instruments = tuple(
        [_instrument(i, active=True, exchange="NYSE") for i in range(5)]
        + [_instrument(100, active=False, exchange="NYSE")]
    )
    policy = EodhdRepresentativeSamplePolicy(active_count=3, delisted_count=1, min_exchanges=2)

    try:
        select_eodhd_representative_sample(instruments, policy=policy)
    except EodhdRepresentativeSampleError as exc:
        assert "exchanges" in str(exc)
    else:
        raise AssertionError("expected representative sample failure")


def test_campaign_payload_matches_strict_eodhd_plan_schema() -> None:
    instruments = tuple(
        [_instrument(i, active=True, exchange="NYSE" if i % 2 else "NASDAQ") for i in range(6)]
        + [_instrument(100 + i, active=False, exchange="NYSE") for i in range(2)]
    )
    selection = select_eodhd_representative_sample(
        instruments,
        policy=EodhdRepresentativeSamplePolicy(active_count=4, delisted_count=2, min_exchanges=2),
    )

    payload = campaign_payload(selection)

    assert payload["schema_version"] == "eodhd-campaign-plan-v0.1"
    assert payload["plan_version"] == "phase1-representative-v0.1"
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 6
    assert {case["expected_state"] for case in cases} == {"active", "delisted"}
    assert all(str(case["dataset_version"]).startswith("eodhd-representative-") for case in cases)
