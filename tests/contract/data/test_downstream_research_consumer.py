from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.data.serving import ResearchDataRequest, serve_research_bars


@dataclass(frozen=True, slots=True)
class DownstreamSummary:
    """Test-only downstream result derived solely from the stable ResearchBar contract."""

    eligible_rows: int
    mean_close: float
    dataset_version: DatasetVersion


def consume_research_bars(rows: tuple[ResearchBar, ...]) -> DownstreamSummary:
    """Represent a downstream analytical module without provider-native imports."""

    eligible = tuple(row for row in rows if row.eligibility)
    if not eligible:
        raise ValueError("downstream test consumer requires at least one eligible row")
    dataset_versions = {row.dataset_version for row in rows}
    if len(dataset_versions) != 1:
        raise ValueError("downstream test consumer requires one immutable dataset version")
    return DownstreamSummary(
        eligible_rows=len(eligible),
        mean_close=sum(row.close for row in eligible) / len(eligible),
        dataset_version=next(iter(dataset_versions)),
    )


def _bar(
    instrument_id: InstrumentId,
    trade_date: date,
    close: float,
    *,
    dataset_version: DatasetVersion,
) -> DailyBar:
    return DailyBar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open_raw=close - 1.0,
        high_raw=close + 1.0,
        low_raw=close - 2.0,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close - 1.0,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 2.0,
        close_split_adjusted=close,
        provider_id="canonical_primary",
        dataset_version=dataset_version,
        quality_status=QualityStatus.PASS,
    )


def test_downstream_module_consumes_only_research_contract() -> None:
    version = DatasetVersion("us-equities-test-v1")
    instrument = InstrumentId("tsi_test_instrument")
    bars = (
        _bar(instrument, date(2024, 1, 2), 100.0, dataset_version=version),
        _bar(instrument, date(2024, 1, 3), 104.0, dataset_version=version),
    )
    request = ResearchDataRequest(
        dataset_version=version,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
        allowed_quality_states=frozenset({QualityStatus.PASS}),
    )
    eligibility = {
        (instrument, date(2024, 1, 2)): True,
        (instrument, date(2024, 1, 3)): True,
    }

    research_rows = serve_research_bars(
        bars,
        eligibility_by_key=eligibility,
        request=request,
    )
    result = consume_research_bars(research_rows)

    assert result.eligible_rows == 2
    assert result.mean_close == 102.0
    assert result.dataset_version == version
    assert all(row.price_representation is PriceRepresentation.SPLIT_ADJUSTED for row in research_rows)
