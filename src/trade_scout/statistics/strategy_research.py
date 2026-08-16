"""Generic exploratory strategy research over immutable canonical daily bars.

This module reconciles the earlier market-analysis strategy workbench with the accepted
research architecture. Strategy conditions are safe feature expressions, signal formation is
point-in-time, ranking is cross-sectional by session, and post-signal outcomes delegate to the
canonical OutcomePath engine rather than reimplementing forward-path semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from statistics import median

from trade_scout.data.contracts import (
    DailyBar,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    to_research_bar,
)
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.expression import compile_feature_expression
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET,
    MARKET_ANALYSIS_FEATURE_SET_VERSION,
    compute_market_analysis_feature_frame,
)
from trade_scout.outcomes.path import OutcomePath, OutcomePathStatus, measure_outcome_paths

_ALLOWED_FEATURES = frozenset(
    definition.feature_name for definition in MARKET_ANALYSIS_FEATURE_SET.definitions
)


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """Immutable exploratory strategy definition expressed over registered features."""

    strategy_id: str
    name: str
    expression: str
    rank_feature: str = "return_20"
    descending: bool = True
    per_session_limit: int = 100
    description: str = ""

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not self.name.strip():
            raise ValueError("strategy name must be non-empty")
        if not self.expression.strip():
            raise ValueError("strategy expression must be non-empty")
        if self.rank_feature not in _ALLOWED_FEATURES:
            raise ValueError(f"unknown strategy rank feature {self.rank_feature!r}")
        if not 1 <= self.per_session_limit <= 500:
            raise ValueError("per_session_limit must be between 1 and 500")


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """One selected point-in-time instrument/session strategy event."""

    strategy_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    rank_feature: str
    rank_value: float
    dataset_version: str
    feature_set_version: str = MARKET_ANALYSIS_FEATURE_SET_VERSION
    event_definition_version: str = "feature-expression-strategy-signal-v0.1"

    @property
    def event_id(self) -> str:
        return (
            f"{self.instrument_id}:{self.event_definition_version}:"
            f"{self.strategy_id}:{self.signal_date.isoformat()}"
        )


@dataclass(frozen=True, slots=True)
class StrategyHorizonSummary:
    """Descriptive complete-path summary for one forward horizon."""

    horizon: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    median_mfe: float | None
    median_mae: float | None
    median_drawdown_lower_bound: float | None
    median_drawdown_upper_bound: float | None


@dataclass(frozen=True, slots=True)
class StrategyResearchReport:
    """Exploratory signal and outcome record for one immutable strategy definition."""

    strategy: StrategyDefinition
    dataset_version: str
    feature_set_version: str
    instrument_count: int
    signal_count: int
    horizons: tuple[int, ...]
    signal_start: date | None
    signal_end: date | None
    signals: tuple[StrategySignal, ...]
    outcomes: tuple[OutcomePath, ...]
    summaries: tuple[StrategyHorizonSummary, ...]
    warnings: tuple[str, ...]
    research_state: str = "EXPLORATORY"
    report_definition_version: str = "feature-strategy-research-v0.1"


def run_feature_strategy_research(
    bars: Iterable[DailyBar],
    *,
    strategy: StrategyDefinition,
    horizons: tuple[int, ...] = (5, 20, 60),
    signal_start: date | None = None,
    signal_end: date | None = None,
) -> StrategyResearchReport:
    """Evaluate a feature-expression strategy without provider calls or future-data leakage."""

    materialized = tuple(bars)
    if not materialized:
        raise ValueError("strategy research requires canonical daily bars")
    if not horizons or any(item < 1 for item in horizons):
        raise ValueError("horizons must contain positive session counts")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")
    if signal_start is not None and signal_end is not None and signal_start > signal_end:
        raise ValueError("signal_start cannot be after signal_end")

    versions = {str(item.dataset_version) for item in materialized}
    if len(versions) != 1:
        raise ValueError("strategy research cannot mix canonical dataset versions")
    if any(item.quality_status is not QualityStatus.PASS for item in materialized):
        raise ValueError("strategy research requires PASS canonical bars")
    dataset_version = next(iter(versions))

    by_instrument: dict[InstrumentId, list[DailyBar]] = {}
    for bar in materialized:
        by_instrument.setdefault(bar.instrument_id, []).append(bar)
    ordered_by_instrument = {
        instrument_id: tuple(sorted(rows, key=lambda item: item.trade_date))
        for instrument_id, rows in by_instrument.items()
    }
    for instrument_id, rows in ordered_by_instrument.items():
        dates = tuple(item.trade_date for item in rows)
        if len(dates) != len(set(dates)):
            raise ValueError(f"duplicate canonical dates for {instrument_id}")

    expression = compile_feature_expression(strategy.expression, allowed_names=_ALLOWED_FEATURES)
    candidates_by_date: dict[date, list[StrategySignal]] = {}

    for instrument_id, rows in ordered_by_instrument.items():
        frame = compute_market_analysis_feature_frame(rows)
        values_by_date: dict[date, dict[str, float | None]] = {}
        for item in frame:
            values_by_date.setdefault(item.trade_date, {})[item.feature_name] = (
                float(item.value)
                if item.availability_status is FeatureAvailabilityStatus.AVAILABLE
                and item.value is not None
                else None
            )
        index_by_date = {bar.trade_date: index for index, bar in enumerate(rows)}
        for trade_date, values in values_by_date.items():
            if signal_start is not None and trade_date < signal_start:
                continue
            if signal_end is not None and trade_date > signal_end:
                continue
            if not expression.evaluate(values):
                continue
            rank_value = values.get(strategy.rank_feature)
            if rank_value is None:
                continue
            candidates_by_date.setdefault(trade_date, []).append(
                StrategySignal(
                    strategy_id=strategy.strategy_id,
                    instrument_id=instrument_id,
                    signal_date=trade_date,
                    signal_index=index_by_date[trade_date],
                    rank_feature=strategy.rank_feature,
                    rank_value=rank_value,
                    dataset_version=dataset_version,
                )
            )

    selected: list[StrategySignal] = []
    for trade_date in sorted(candidates_by_date):
        daily = candidates_by_date[trade_date]
        if strategy.descending:
            daily.sort(key=lambda item: (-item.rank_value, str(item.instrument_id)))
        else:
            daily.sort(key=lambda item: (item.rank_value, str(item.instrument_id)))
        selected.extend(daily[: strategy.per_session_limit])
    signals = tuple(selected)

    signals_by_instrument: dict[InstrumentId, list[StrategySignal]] = {}
    for signal in signals:
        signals_by_instrument.setdefault(signal.instrument_id, []).append(signal)

    outcomes: list[OutcomePath] = []
    for instrument_id, instrument_signals in signals_by_instrument.items():
        research_bars = _research_bars(ordered_by_instrument[instrument_id])
        outcomes.extend(
            measure_outcome_paths(
                research_bars,
                tuple(instrument_signals),
                horizons=horizons,
            )
        )

    ordered_outcomes = tuple(
        sorted(
            outcomes,
            key=lambda item: (
                item.signal_date,
                str(item.instrument_id),
                item.horizon,
            ),
        )
    )
    return StrategyResearchReport(
        strategy=strategy,
        dataset_version=dataset_version,
        feature_set_version=MARKET_ANALYSIS_FEATURE_SET_VERSION,
        instrument_count=len(ordered_by_instrument),
        signal_count=len(signals),
        horizons=horizons,
        signal_start=signal_start,
        signal_end=signal_end,
        signals=signals,
        outcomes=ordered_outcomes,
        summaries=_summaries(ordered_outcomes, horizons),
        warnings=(
            (
                "Exploratory descriptive research only; results are not validation "
                "or production eligibility."
            ),
            (
                "The supplied canonical instrument cohort is evaluated as provided. "
                "This runner does not invent historical index membership or "
                "survivorship-bias corrections."
            ),
            (
                "Strategy selection is point-in-time and post-signal paths use the "
                "canonical OutcomePath engine with next-session-open entry and explicit "
                "daily-bar ambiguity."
            ),
        ),
    )


def available_strategy_features() -> tuple[str, ...]:
    """Return the registered feature names accepted by strategy expressions."""

    return tuple(sorted(_ALLOWED_FEATURES))


def _research_bars(rows: tuple[DailyBar, ...]) -> tuple[ResearchBar, ...]:
    return tuple(
        to_research_bar(
            bar,
            representation=PriceRepresentation.SPLIT_ADJUSTED,
            eligibility=True,
        )
        for bar in rows
    )


def _summaries(
    outcomes: tuple[OutcomePath, ...], horizons: tuple[int, ...]
) -> tuple[StrategyHorizonSummary, ...]:
    summaries: list[StrategyHorizonSummary] = []
    for horizon in horizons:
        complete = tuple(
            item
            for item in outcomes
            if item.horizon == horizon and item.status is OutcomePathStatus.COMPLETE
        )
        returns = tuple(
            float(item.forward_return) for item in complete if item.forward_return is not None
        )
        if not returns:
            summaries.append(
                StrategyHorizonSummary(
                    horizon=horizon,
                    sample_size=0,
                    mean_return=None,
                    median_return=None,
                    positive_fraction=None,
                    median_mfe=None,
                    median_mae=None,
                    median_drawdown_lower_bound=None,
                    median_drawdown_upper_bound=None,
                )
            )
            continue
        summaries.append(
            StrategyHorizonSummary(
                horizon=horizon,
                sample_size=len(returns),
                mean_return=sum(returns) / len(returns),
                median_return=median(returns),
                positive_fraction=sum(value > 0 for value in returns) / len(returns),
                median_mfe=median(float(item.mfe) for item in complete if item.mfe is not None),
                median_mae=median(float(item.mae) for item in complete if item.mae is not None),
                median_drawdown_lower_bound=median(
                    float(item.max_drawdown_lower_bound)
                    for item in complete
                    if item.max_drawdown_lower_bound is not None
                ),
                median_drawdown_upper_bound=median(
                    float(item.max_drawdown_upper_bound)
                    for item in complete
                    if item.max_drawdown_upper_bound is not None
                ),
            )
        )
    return tuple(summaries)


__all__ = [
    "StrategyDefinition",
    "StrategyHorizonSummary",
    "StrategyResearchReport",
    "StrategySignal",
    "available_strategy_features",
    "run_feature_strategy_research",
]
