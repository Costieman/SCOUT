from collections.abc import Sequence
from datetime import date

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.data.serving import (
    DuplicateResearchBarError,
    MissingEligibilityError,
    ResearchDataContractError,
    ResearchDataRequest,
    ResearchDatasetVersionError,
    serve_research_bars,
)

VERSION = DatasetVersion("equities_daily_v1.0.0")


def _bar(
    instrument_id: str,
    trade_date: date,
    *,
    quality_status: QualityStatus = QualityStatus.PASS,
    dataset_version: DatasetVersion = VERSION,
    adjusted: bool = True,
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=100.0,
        high_raw=105.0,
        low_raw=99.0,
        close_raw=103.0,
        volume_raw=1_000_000,
        split_factor=0.5,
        dividend_cash=0.0,
        open_split_adjusted=50.0 if adjusted else None,
        high_split_adjusted=52.5 if adjusted else None,
        low_split_adjusted=49.5 if adjusted else None,
        close_split_adjusted=51.5 if adjusted else None,
        provider_id="primary",
        dataset_version=dataset_version,
        quality_status=quality_status,
    )


def _request(
    *,
    representation: PriceRepresentation = PriceRepresentation.RAW,
    allowed_quality_states: frozenset[QualityStatus] = frozenset({QualityStatus.PASS}),
) -> ResearchDataRequest:
    return ResearchDataRequest(
        dataset_version=VERSION,
        start=date(2026, 8, 6),
        end=date(2026, 8, 8),
        price_representation=representation,
        allowed_quality_states=allowed_quality_states,
    )


def _downstream_consumer(rows: Sequence[ResearchBar]) -> tuple[int, float, int]:
    """Represent a downstream module that knows only the stable ResearchBar contract."""

    return len(rows), sum(row.close for row in rows), sum(row.eligibility for row in rows)


def test_research_contract_serves_point_in_time_eligibility_deterministically() -> None:
    first = _bar("tsi-2", date(2026, 8, 7))
    second = _bar("tsi-1", date(2026, 8, 7))
    eligibility = {
        (first.instrument_id, first.trade_date): False,
        (second.instrument_id, second.trade_date): True,
    }

    rows = serve_research_bars(
        (first, second),
        eligibility_by_key=eligibility,
        request=_request(),
    )

    assert [str(row.instrument_id) for row in rows] == ["tsi-1", "tsi-2"]
    assert rows[0].eligibility is True
    assert rows[1].eligibility is False
    assert _downstream_consumer(rows) == (2, 206.0, 1)


def test_split_adjusted_representation_is_explicit() -> None:
    bar = _bar("tsi-1", date(2026, 8, 7))

    rows = serve_research_bars(
        (bar,),
        eligibility_by_key={(bar.instrument_id, bar.trade_date): True},
        request=_request(representation=PriceRepresentation.SPLIT_ADJUSTED),
    )

    assert rows[0].close == 51.5
    assert rows[0].price_representation is PriceRepresentation.SPLIT_ADJUSTED


def test_missing_point_in_time_eligibility_fails_instead_of_assuming_true() -> None:
    bar = _bar("tsi-1", date(2026, 8, 7))

    with pytest.raises(MissingEligibilityError):
        serve_research_bars(
            (bar,),
            eligibility_by_key={},
            request=_request(),
        )


def test_dataset_version_mismatch_fails_instead_of_silently_filtering() -> None:
    bar = _bar(
        "tsi-1",
        date(2026, 8, 7),
        dataset_version=DatasetVersion("equities_daily_v1.0.1"),
    )

    with pytest.raises(ResearchDatasetVersionError):
        serve_research_bars(
            (bar,),
            eligibility_by_key={(bar.instrument_id, bar.trade_date): True},
            request=_request(),
        )


def test_warn_records_are_visible_only_when_request_explicitly_allows_them() -> None:
    bar = _bar("tsi-1", date(2026, 8, 7), quality_status=QualityStatus.WARN)
    eligibility = {(bar.instrument_id, bar.trade_date): True}

    excluded = serve_research_bars(
        (bar,),
        eligibility_by_key=eligibility,
        request=_request(),
    )
    included = serve_research_bars(
        (bar,),
        eligibility_by_key=eligibility,
        request=_request(
            allowed_quality_states=frozenset({QualityStatus.PASS, QualityStatus.WARN})
        ),
    )

    assert excluded == ()
    assert included[0].quality_status is QualityStatus.WARN


def test_blocked_quality_states_cannot_be_enabled_for_research_serving() -> None:
    with pytest.raises(ResearchDataContractError, match="blocked quality states"):
        _request(allowed_quality_states=frozenset({QualityStatus.QUARANTINE}))


def test_blocked_record_reaching_serving_fails_even_when_not_requested() -> None:
    bar = _bar("tsi-1", date(2026, 8, 7), quality_status=QualityStatus.REJECT)

    with pytest.raises(ResearchDataContractError, match="blocked quality state"):
        serve_research_bars(
            (bar,),
            eligibility_by_key={(bar.instrument_id, bar.trade_date): True},
            request=_request(),
        )


def test_duplicate_canonical_key_fails_at_research_boundary() -> None:
    bar = _bar("tsi-1", date(2026, 8, 7))

    with pytest.raises(DuplicateResearchBarError):
        serve_research_bars(
            (bar, bar),
            eligibility_by_key={(bar.instrument_id, bar.trade_date): True},
            request=_request(),
        )


def test_bars_outside_requested_period_are_not_served() -> None:
    bar = _bar("tsi-1", date(2026, 8, 5))

    rows = serve_research_bars(
        (bar,),
        eligibility_by_key={},
        request=_request(),
    )

    assert rows == ()
