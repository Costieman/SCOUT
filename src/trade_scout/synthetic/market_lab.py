"""Reusable deterministic synthetic market histories with explicit expected behavior.

The laboratory deliberately produces vendor-independent ``ResearchBar`` fixtures so analytical
modules can be exercised without access to the canonical market-data store. Each scenario also
carries explicit annotations describing the market behavior intentionally embedded in the series.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from types import MappingProxyType

from trade_scout.data.contracts import (
    CorporateActionRecord,
    CorporateActionType,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)

SYNTHETIC_DATASET_VERSION = DatasetVersion("synthetic-market-lab-v1")
AnnotationValue = str | int | float | bool | None


class SyntheticScenarioKind(StrEnum):
    """Canonical reusable scenarios supported by the initial synthetic market laboratory."""

    CLEAN_TREND = "clean_trend"
    CONSOLIDATION_BREAKOUT = "consolidation_breakout"
    FALSE_BREAKOUT = "false_breakout"
    MISSING_BARS = "missing_bars"
    SPLIT_DISCONTINUITY = "split_discontinuity"
    VOLATILITY_SHOCK = "volatility_shock"
    NESTED_BASES = "nested_bases"
    GAP_DOWN = "gap_down"
    STOP_OUT = "stop_out"
    AMBIGUOUS_DAILY_BAR = "ambiguous_daily_bar"


class SyntheticAnnotationKind(StrEnum):
    """Known behaviors embedded in synthetic histories."""

    TREND = "trend"
    CONSOLIDATION = "consolidation"
    BREAKOUT = "breakout"
    FALSE_BREAKOUT = "false_breakout"
    MISSING_BAR = "missing_bar"
    SPLIT = "split"
    VOLATILITY_SHOCK = "volatility_shock"
    NESTED_BASE = "nested_base"
    GAP_DOWN = "gap_down"
    STOP_HIT = "stop_hit"
    AMBIGUOUS_BAR = "ambiguous_bar"


@dataclass(frozen=True, slots=True)
class SyntheticAnnotation:
    """Expected behavior intentionally embedded within a synthetic market scenario."""

    kind: SyntheticAnnotationKind
    start_date: date
    end_date: date
    values: Mapping[str, AnnotationValue]

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("annotation start_date must not be after end_date")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class SyntheticMarketScenario:
    """One controlled market history and its known expected behavior."""

    scenario_id: str
    kind: SyntheticScenarioKind
    description: str
    raw_bars: tuple[ResearchBar, ...]
    annotations: tuple[SyntheticAnnotation, ...]
    split_adjusted_bars: tuple[ResearchBar, ...] | None = None
    corporate_actions: tuple[CorporateActionRecord, ...] = ()

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.description:
            raise ValueError("scenario_id and description must not be empty")
        if not self.raw_bars:
            raise ValueError("synthetic scenarios must contain at least one raw bar")
        self._validate_bars(self.raw_bars, PriceRepresentation.RAW)
        if self.split_adjusted_bars is not None:
            self._validate_bars(
                self.split_adjusted_bars,
                PriceRepresentation.SPLIT_ADJUSTED,
            )
            raw_dates = tuple(bar.trade_date for bar in self.raw_bars)
            adjusted_dates = tuple(bar.trade_date for bar in self.split_adjusted_bars)
            if raw_dates != adjusted_dates:
                raise ValueError("raw and split-adjusted scenarios must have identical dates")

    @staticmethod
    def _validate_bars(
        bars: Sequence[ResearchBar],
        representation: PriceRepresentation,
    ) -> None:
        first_instrument = bars[0].instrument_id
        previous_date: date | None = None
        for bar in bars:
            if bar.instrument_id != first_instrument:
                raise ValueError("all bars in a synthetic scenario must use one instrument_id")
            if bar.price_representation is not representation:
                raise ValueError(
                    "synthetic bar price representation does not match scenario series"
                )
            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                raise ValueError("synthetic OHLC envelope is internally inconsistent")
            if bar.low > bar.high:
                raise ValueError("synthetic low cannot exceed high")
            if previous_date is not None and bar.trade_date <= previous_date:
                raise ValueError("synthetic bar dates must be strictly increasing")
            previous_date = bar.trade_date

    def bars(
        self,
        representation: PriceRepresentation = PriceRepresentation.RAW,
    ) -> tuple[ResearchBar, ...]:
        """Return the requested explicit price representation for the scenario."""

        if representation is PriceRepresentation.RAW:
            return self.raw_bars
        if self.split_adjusted_bars is None:
            raise ValueError(f"split-adjusted bars unavailable for scenario {self.scenario_id}")
        return self.split_adjusted_bars


def _trading_dates(start: date, count: int) -> tuple[date, ...]:
    if count <= 0:
        raise ValueError("count must be positive")
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def _bar(
    *,
    instrument_id: InstrumentId,
    trade_date: date,
    open_price: float,
    close_price: float,
    high_price: float | None = None,
    low_price: float | None = None,
    volume: float = 1_000_000.0,
    representation: PriceRepresentation = PriceRepresentation.RAW,
) -> ResearchBar:
    if open_price <= 0 or close_price <= 0 or volume < 0:
        raise ValueError("synthetic prices must be positive and volume non-negative")
    high = high_price if high_price is not None else max(open_price, close_price) * 1.01
    low = low_price if low_price is not None else min(open_price, close_price) * 0.99
    return ResearchBar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open=open_price,
        high=high,
        low=low,
        close=close_price,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=SYNTHETIC_DATASET_VERSION,
        price_representation=representation,
    )


def _bars_from_closes(
    *,
    scenario_id: str,
    dates: Sequence[date],
    closes: Sequence[float],
    representation: PriceRepresentation = PriceRepresentation.RAW,
    volume: float = 1_000_000.0,
) -> tuple[ResearchBar, ...]:
    if len(dates) != len(closes):
        raise ValueError("dates and closes must have equal length")
    instrument_id = InstrumentId(f"SYN-{scenario_id.upper()}")
    bars: list[ResearchBar] = []
    previous_close = closes[0]
    for trade_date, close_price in zip(dates, closes, strict=True):
        bars.append(
            _bar(
                instrument_id=instrument_id,
                trade_date=trade_date,
                open_price=previous_close,
                close_price=close_price,
                volume=volume,
                representation=representation,
            )
        )
        previous_close = close_price
    return tuple(bars)


def clean_trend_scenario() -> SyntheticMarketScenario:
    """Create a monotonic low-noise uptrend with no embedded reversal or discontinuity."""

    dates = _trading_dates(date(2020, 1, 2), 60)
    closes = tuple(100.0 + 0.8 * index for index in range(len(dates)))
    bars = _bars_from_closes(
        scenario_id="clean-trend",
        dates=dates,
        closes=closes,
    )
    return SyntheticMarketScenario(
        scenario_id="clean-trend",
        kind=SyntheticScenarioKind.CLEAN_TREND,
        description="Steady deterministic uptrend used as a positive trend-control history.",
        raw_bars=bars,
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.TREND,
                start_date=dates[0],
                end_date=dates[-1],
                values={"direction": "up", "monotonic_close": True},
            ),
        ),
    )


def consolidation_breakout_scenario() -> SyntheticMarketScenario:
    """Create an uptrend, a tight base, and a decisive breakout."""

    dates = _trading_dates(date(2020, 4, 1), 55)
    trend = [100.0 + 0.7 * index for index in range(20)]
    base = [114.0 + (0.35 if index % 2 == 0 else -0.35) for index in range(20)]
    breakout = [
        116.0,
        118.0,
        120.0,
        122.0,
        124.0,
        126.0,
        127.0,
        128.0,
        129.0,
        130.0,
        131.0,
        132.0,
        133.0,
        134.0,
        135.0,
    ]
    closes = tuple(trend + base + breakout)
    bars = _bars_from_closes(
        scenario_id="consolidation-breakout",
        dates=dates,
        closes=closes,
    )
    return SyntheticMarketScenario(
        scenario_id="consolidation-breakout",
        kind=SyntheticScenarioKind.CONSOLIDATION_BREAKOUT,
        description=(
            "Prior uptrend followed by a tight twenty-session base and confirmed upside breakout."
        ),
        raw_bars=bars,
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.CONSOLIDATION,
                start_date=dates[20],
                end_date=dates[39],
                values={"upper_boundary": 114.35, "lower_boundary": 113.65},
            ),
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.BREAKOUT,
                start_date=dates[40],
                end_date=dates[40],
                values={"direction": "up", "reference_boundary": 114.35},
            ),
        ),
    )


def false_breakout_scenario() -> SyntheticMarketScenario:
    """Create a tight base, one apparent upside breakout, then immediate failure."""

    dates = _trading_dates(date(2020, 7, 1), 42)
    lead_in = [100.0 + 0.4 * index for index in range(12)]
    base = [104.5 + (0.25 if index % 2 == 0 else -0.25) for index in range(20)]
    failure = [106.5, 103.5, 102.5, 101.5, 101.0, 100.5, 100.0, 99.5, 99.0, 98.5]
    closes = tuple(lead_in + base + failure)
    bars = _bars_from_closes(
        scenario_id="false-breakout",
        dates=dates,
        closes=closes,
    )
    return SyntheticMarketScenario(
        scenario_id="false-breakout",
        kind=SyntheticScenarioKind.FALSE_BREAKOUT,
        description="Base with a one-session upside escape followed by immediate structural failure.",
        raw_bars=bars,
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.CONSOLIDATION,
                start_date=dates[12],
                end_date=dates[31],
                values={"upper_boundary": 104.75, "lower_boundary": 104.25},
            ),
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.FALSE_BREAKOUT,
                start_date=dates[32],
                end_date=dates[33],
                values={"breakout_close": 106.5, "failure_close": 103.5},
            ),
        ),
    )


def missing_bars_scenario() -> SyntheticMarketScenario:
    """Create a regular trend with known omitted trading sessions."""

    complete_dates = _trading_dates(date(2020, 9, 1), 40)
    missing_indices = (10, 11, 25)
    retained_dates = tuple(
        trade_date
        for index, trade_date in enumerate(complete_dates)
        if index not in missing_indices
    )
    closes = tuple(100.0 + 0.3 * index for index in range(len(retained_dates)))
    bars = _bars_from_closes(
        scenario_id="missing-bars",
        dates=retained_dates,
        closes=closes,
    )
    annotations = tuple(
        SyntheticAnnotation(
            kind=SyntheticAnnotationKind.MISSING_BAR,
            start_date=complete_dates[index],
            end_date=complete_dates[index],
            values={"expected_session": True},
        )
        for index in missing_indices
    )
    return SyntheticMarketScenario(
        scenario_id="missing-bars",
        kind=SyntheticScenarioKind.MISSING_BARS,
        description="Regular series with three intentionally omitted expected trading sessions.",
        raw_bars=bars,
        annotations=annotations,
    )


def split_discontinuity_scenario() -> SyntheticMarketScenario:
    """Create a 2-for-1 split with raw discontinuity and continuous split-adjusted history."""

    dates = _trading_dates(date(2020, 11, 2), 30)
    split_index = 15
    pre_split_raw = [100.0 + index for index in range(split_index)]
    post_split_raw = [57.5 + 0.5 * index for index in range(len(dates) - split_index)]
    raw_closes = tuple(pre_split_raw + post_split_raw)
    adjusted_closes = tuple(
        close / 2.0 if index < split_index else close
        for index, close in enumerate(raw_closes)
    )

    raw_bars = list(
        _bars_from_closes(
            scenario_id="split-discontinuity",
            dates=dates,
            closes=raw_closes,
        )
    )
    instrument_id = raw_bars[0].instrument_id
    split_date = dates[split_index]
    raw_bars[split_index] = _bar(
        instrument_id=instrument_id,
        trade_date=split_date,
        open_price=57.0,
        close_price=raw_closes[split_index],
        high_price=58.0,
        low_price=56.5,
    )
    adjusted_bars = _bars_from_closes(
        scenario_id="split-discontinuity",
        dates=dates,
        closes=adjusted_closes,
        representation=PriceRepresentation.SPLIT_ADJUSTED,
    )
    action = CorporateActionRecord(
        action_id="SYN-SPLIT-2-FOR-1",
        instrument_id=instrument_id,
        action_type=CorporateActionType.SPLIT,
        effective_date=split_date,
        provider_id="synthetic-market-lab",
        source_event_id=None,
        source_fields={"split_ratio": 2.0},
    )
    return SyntheticMarketScenario(
        scenario_id="split-discontinuity",
        kind=SyntheticScenarioKind.SPLIT_DISCONTINUITY,
        description=(
            "Two-for-one split with a raw-price discontinuity and continuous adjusted series."
        ),
        raw_bars=tuple(raw_bars),
        split_adjusted_bars=adjusted_bars,
        corporate_actions=(action,),
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.SPLIT,
                start_date=split_date,
                end_date=split_date,
                values={"ratio": 2.0, "raw_discontinuity_expected": True},
            ),
        ),
    )


def volatility_shock_scenario() -> SyntheticMarketScenario:
    """Create stable trading followed by one extreme-range volatility shock."""

    dates = _trading_dates(date(2021, 1, 4), 35)
    closes = [100.0 + (0.2 if index % 2 == 0 else -0.2) for index in range(35)]
    bars = list(
        _bars_from_closes(
            scenario_id="volatility-shock",
            dates=dates,
            closes=closes,
        )
    )
    shock_index = 20
    shock_date = dates[shock_index]
    instrument_id = bars[shock_index].instrument_id
    bars[shock_index] = _bar(
        instrument_id=instrument_id,
        trade_date=shock_date,
        open_price=100.2,
        close_price=108.0,
        high_price=118.0,
        low_price=89.0,
        volume=5_000_000.0,
    )
    return SyntheticMarketScenario(
        scenario_id="volatility-shock",
        kind=SyntheticScenarioKind.VOLATILITY_SHOCK,
        description=(
            "Low-volatility history interrupted by one extreme intraday range and volume shock."
        ),
        raw_bars=tuple(bars),
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.VOLATILITY_SHOCK,
                start_date=shock_date,
                end_date=shock_date,
                values={"high": 118.0, "low": 89.0, "volume": 5_000_000.0},
            ),
        ),
    )


def nested_bases_scenario() -> SyntheticMarketScenario:
    """Create a broad consolidation containing a tighter nested base before breakout."""

    dates = _trading_dates(date(2021, 3, 1), 50)
    lead_in = [100.0 + 0.5 * index for index in range(15)]
    broad = [107.0 + (1.5 if index % 2 == 0 else -1.5) for index in range(15)]
    inner = [107.0 + (0.35 if index % 2 == 0 else -0.35) for index in range(10)]
    breakout = [109.5, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0]
    closes = tuple(lead_in + broad + inner + breakout)
    bars = _bars_from_closes(
        scenario_id="nested-bases",
        dates=dates,
        closes=closes,
    )
    return SyntheticMarketScenario(
        scenario_id="nested-bases",
        kind=SyntheticScenarioKind.NESTED_BASES,
        description="Broad base containing a tighter nested consolidation before upside resolution.",
        raw_bars=bars,
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.CONSOLIDATION,
                start_date=dates[15],
                end_date=dates[39],
                values={
                    "scope": "outer",
                    "upper_boundary": 108.5,
                    "lower_boundary": 105.5,
                },
            ),
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.NESTED_BASE,
                start_date=dates[30],
                end_date=dates[39],
                values={
                    "scope": "inner",
                    "upper_boundary": 107.35,
                    "lower_boundary": 106.65,
                },
            ),
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.BREAKOUT,
                start_date=dates[40],
                end_date=dates[40],
                values={"direction": "up"},
            ),
        ),
    )


def gap_down_scenario() -> SyntheticMarketScenario:
    """Create a deterministic overnight gap-down discontinuity."""

    dates = _trading_dates(date(2021, 5, 3), 25)
    closes = tuple(100.0 + 0.25 * index for index in range(25))
    bars = list(
        _bars_from_closes(
            scenario_id="gap-down",
            dates=dates,
            closes=closes,
        )
    )
    gap_index = 15
    prior_close = bars[gap_index - 1].close
    gap_date = dates[gap_index]
    instrument_id = bars[gap_index].instrument_id
    gap_open = prior_close * 0.88
    bars[gap_index] = _bar(
        instrument_id=instrument_id,
        trade_date=gap_date,
        open_price=gap_open,
        close_price=gap_open * 0.98,
        high_price=gap_open * 1.01,
        low_price=gap_open * 0.95,
        volume=3_000_000.0,
    )
    return SyntheticMarketScenario(
        scenario_id="gap-down",
        kind=SyntheticScenarioKind.GAP_DOWN,
        description="Overnight open twelve percent below the prior close with elevated volume.",
        raw_bars=tuple(bars),
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.GAP_DOWN,
                start_date=gap_date,
                end_date=gap_date,
                values={
                    "prior_close": prior_close,
                    "open": gap_open,
                    "gap_fraction": -0.12,
                },
            ),
        ),
    )


def stop_out_scenario() -> SyntheticMarketScenario:
    """Create a path that breaches a fixed stop before later recovering above entry."""

    dates = _trading_dates(date(2021, 7, 1), 12)
    closes = [100.0, 101.0, 99.0, 97.0, 96.0, 98.0, 101.0, 104.0, 106.0, 108.0, 110.0, 112.0]
    bars = list(
        _bars_from_closes(
            scenario_id="stop-out",
            dates=dates,
            closes=closes,
        )
    )
    stop_index = 4
    instrument_id = bars[stop_index].instrument_id
    bars[stop_index] = _bar(
        instrument_id=instrument_id,
        trade_date=dates[stop_index],
        open_price=97.0,
        close_price=96.0,
        high_price=97.5,
        low_price=94.0,
    )
    return SyntheticMarketScenario(
        scenario_id="stop-out",
        kind=SyntheticScenarioKind.STOP_OUT,
        description=(
            "Entry at 100, subsequent 95 stop breach, then later recovery above the entry price."
        ),
        raw_bars=tuple(bars),
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.STOP_HIT,
                start_date=dates[stop_index],
                end_date=dates[stop_index],
                values={
                    "entry_price": 100.0,
                    "stop_price": 95.0,
                    "intraday_low": 94.0,
                },
            ),
        ),
    )


def ambiguous_daily_bar_scenario() -> SyntheticMarketScenario:
    """Create a daily bar where both stop and target are touched with unknown intraday order."""

    dates = _trading_dates(date(2021, 9, 1), 4)
    instrument_id = InstrumentId("SYN-AMBIGUOUS-DAILY-BAR")
    bars = (
        _bar(
            instrument_id=instrument_id,
            trade_date=dates[0],
            open_price=100.0,
            close_price=100.0,
            high_price=101.0,
            low_price=99.0,
        ),
        _bar(
            instrument_id=instrument_id,
            trade_date=dates[1],
            open_price=100.0,
            close_price=101.0,
            high_price=106.0,
            low_price=94.0,
        ),
        _bar(
            instrument_id=instrument_id,
            trade_date=dates[2],
            open_price=101.0,
            close_price=103.0,
        ),
        _bar(
            instrument_id=instrument_id,
            trade_date=dates[3],
            open_price=103.0,
            close_price=104.0,
        ),
    )
    return SyntheticMarketScenario(
        scenario_id="ambiguous-daily-bar",
        kind=SyntheticScenarioKind.AMBIGUOUS_DAILY_BAR,
        description=(
            "One daily bar touches both a 95 stop and 105 target, leaving intraday order unknowable."
        ),
        raw_bars=bars,
        annotations=(
            SyntheticAnnotation(
                kind=SyntheticAnnotationKind.AMBIGUOUS_BAR,
                start_date=dates[1],
                end_date=dates[1],
                values={
                    "entry_price": 100.0,
                    "stop_price": 95.0,
                    "target_price": 105.0,
                },
            ),
        ),
    )


def standard_market_laboratory() -> Mapping[SyntheticScenarioKind, SyntheticMarketScenario]:
    """Build the canonical deterministic scenario suite for analytical integration tests."""

    scenarios = (
        clean_trend_scenario(),
        consolidation_breakout_scenario(),
        false_breakout_scenario(),
        missing_bars_scenario(),
        split_discontinuity_scenario(),
        volatility_shock_scenario(),
        nested_bases_scenario(),
        gap_down_scenario(),
        stop_out_scenario(),
        ambiguous_daily_bar_scenario(),
    )
    return MappingProxyType({scenario.kind: scenario for scenario in scenarios})
