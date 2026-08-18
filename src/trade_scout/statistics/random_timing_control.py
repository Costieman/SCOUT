"""Deterministic same-instrument randomized timing control for frozen event populations.

This module tests timing information, not strategy selection. It keeps each instrument's complete
source-event count fixed, samples alternative eligible signal dates from that same instrument, and
applies the same hold-to-horizon execution-cost semantics. The result is exploratory control
evidence; it does not correct a broader strategy search or establish validation status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from random import Random

from trade_scout.data.contracts import InstrumentId, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.risk.exit_policies import evaluate_exit_policy_grid, exit_policy_grid
from trade_scout.risk.initial_stops import CostModel


@dataclass(frozen=True, slots=True)
class RandomTimingControlReport:
    """Count-matched randomized eligible-timing evidence for one frozen source event population."""

    sample_size: int
    instrument_count: int
    eligible_timing_count: int
    strategy_mean_return: float
    random_timing_mean_return: float
    excess_vs_random_timing: float
    null_interval_lower: float
    null_interval_upper: float
    one_sided_empirical_p_value: float
    iterations: int
    random_seed: int
    comparator_kind: str = "same_instrument_random_eligible_timing"
    comparator_definition_version: str = "same-instrument-random-timing-v0.1"
    warnings: tuple[str, ...] = (
        "Exploratory control only; the random-timing p-value is not adjusted for broader strategy "
        "search or other hypotheses tested elsewhere.",
        "The control preserves complete source-event counts by instrument, not the original "
        "cross-sectional signal dates or market-regime mix.",
    )


@dataclass(frozen=True, slots=True)
class _RandomTimingEvent:
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    ordinal: int
    event_definition_version: str = "random-eligible-timing-control-v0.1"

    @property
    def event_id(self) -> str:
        return (
            f"{self.instrument_id}:{self.event_definition_version}:"
            f"{self.signal_date.isoformat()}:{self.ordinal}"
        )


def run_same_instrument_random_timing_control(
    research_by_instrument: dict[str, tuple[ResearchBar, ...]],
    source_events: tuple[EventRecord, ...],
    *,
    horizon: int,
    cost_model: CostModel,
    signal_start: date,
    signal_end: date,
    iterations: int = 1000,
    random_seed: int = 20260818,
) -> RandomTimingControlReport:
    """Compare frozen source timing with count-matched randomized dates on the same instruments."""

    if horizon < 1:
        raise ValueError("random-timing horizon must be positive")
    if signal_end < signal_start:
        raise ValueError("random-timing signal_end must be on or after signal_start")
    if not 100 <= iterations <= 10_000:
        raise ValueError("random-timing iterations must be between 100 and 10000")
    if not source_events:
        raise ValueError("random-timing control requires source events")

    hold_policy = exit_policy_grid(
        fixed_percentages=(),
        atr_multiples=(),
        trailing_percentages=(),
        trailing_atr_multiples=(),
    )
    source_by_instrument: dict[str, list[EventRecord]] = {}
    for event in source_events:
        source_by_instrument.setdefault(str(event.instrument_id), []).append(event)

    complete_counts: dict[str, int] = {}
    source_returns: list[float] = []
    for instrument_id, events in sorted(source_by_instrument.items()):
        bars = research_by_instrument.get(instrument_id)
        if bars is None:
            raise ValueError(
                f"random-timing source event references missing instrument {instrument_id}"
            )
        results = evaluate_exit_policy_grid(
            bars,
            tuple(events),
            horizon=horizon,
            policies=hold_policy,
            cost_model=cost_model,
        )
        if results:
            complete_counts[instrument_id] = len(results)
            source_returns.extend(item.realized_return for item in results)

    if not source_returns:
        raise ValueError("random-timing source population has no complete hold-to-horizon events")

    eligible_by_instrument: dict[str, tuple[int, ...]] = {}
    eligible_timing_count = 0
    for instrument_id, count in sorted(complete_counts.items()):
        bars = research_by_instrument[instrument_id]
        indices = tuple(
            index
            for index, bar in enumerate(bars)
            if signal_start <= bar.trade_date <= signal_end
            and index + horizon < len(bars)
        )
        if len(indices) < count:
            raise ValueError(
                "random-timing eligible pool is smaller than the source complete-event count for "
                f"{instrument_id}: eligible={len(indices)}, required={count}"
            )
        eligible_by_instrument[instrument_id] = indices
        eligible_timing_count += len(indices)

    rng = Random(random_seed)
    null_means: list[float] = []
    for iteration in range(iterations):
        sampled_returns: list[float] = []
        for instrument_id, count in sorted(complete_counts.items()):
            bars = research_by_instrument[instrument_id]
            selected = rng.sample(eligible_by_instrument[instrument_id], count)
            events = tuple(
                _RandomTimingEvent(
                    instrument_id=bars[index].instrument_id,
                    signal_date=bars[index].trade_date,
                    signal_index=index,
                    dataset_version=bars[index].dataset_version,
                    ordinal=iteration * max(1, count) + ordinal,
                )
                for ordinal, index in enumerate(sorted(selected))
            )
            results = evaluate_exit_policy_grid(
                bars,
                events,
                horizon=horizon,
                policies=hold_policy,
                cost_model=cost_model,
            )
            if len(results) != count:
                raise RuntimeError(
                    "random-timing sampled an eligible date that did not produce a complete result"
                )
            sampled_returns.extend(item.realized_return for item in results)
        if len(sampled_returns) != len(source_returns):
            raise RuntimeError("random-timing iteration did not preserve the source sample size")
        null_means.append(sum(sampled_returns) / len(sampled_returns))

    strategy_mean = sum(source_returns) / len(source_returns)
    random_mean = sum(null_means) / len(null_means)
    ordered_null = sorted(null_means)
    lower = _empirical_quantile(ordered_null, 0.025)
    upper = _empirical_quantile(ordered_null, 0.975)
    p_value = (1 + sum(value >= strategy_mean for value in null_means)) / (iterations + 1)
    return RandomTimingControlReport(
        sample_size=len(source_returns),
        instrument_count=len(complete_counts),
        eligible_timing_count=eligible_timing_count,
        strategy_mean_return=strategy_mean,
        random_timing_mean_return=random_mean,
        excess_vs_random_timing=strategy_mean - random_mean,
        null_interval_lower=lower,
        null_interval_upper=upper,
        one_sided_empirical_p_value=p_value,
        iterations=iterations,
        random_seed=random_seed,
    )


def _empirical_quantile(ordered: list[float], probability: float) -> float:
    if not ordered:
        raise ValueError("empirical quantile requires observations")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("empirical quantile probability must be between zero and one")
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


__all__ = ["RandomTimingControlReport", "run_same_instrument_random_timing_control"]
