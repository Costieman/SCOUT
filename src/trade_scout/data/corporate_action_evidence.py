"""Provider-neutral corporate-action evidence and price-discontinuity diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from itertools import pairwise

from trade_scout.data.contracts import CorporateActionType
from trade_scout.data.provider import ProviderCorporateAction, ProviderDailyBar


class CorporateActionEvidenceState(StrEnum):
    """Outcome of one auditable corporate-action evidence check."""

    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CorporateActionEvidenceCheck:
    """One assertion about the retrieved corporate-action sample."""

    check_id: str
    state: CorporateActionEvidenceState
    detail: str


@dataclass(frozen=True, slots=True)
class PriceDiscontinuity:
    """Large close-to-close move retained as diagnostic evidence, not automatically repaired."""

    provider_instrument_id: str
    previous_date: date
    trade_date: date
    return_fraction: float
    nearby_action_types: tuple[CorporateActionType, ...]

    @property
    def has_nearby_action(self) -> bool:
        return bool(self.nearby_action_types)


@dataclass(frozen=True, slots=True)
class CorporateActionEvidenceReport:
    """Corporate-action retrieval checks and price-jump diagnostics without acceptance inference."""

    provider_id: str
    checks: tuple[CorporateActionEvidenceCheck, ...]
    discontinuities: tuple[PriceDiscontinuity, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(
            check.state is CorporateActionEvidenceState.PASS for check in self.checks
        )


def evaluate_corporate_action_evidence(
    *,
    provider_id: str,
    actions: Iterable[ProviderCorporateAction],
    bars: Iterable[ProviderDailyBar],
    start: date,
    end: date,
    expected_action_types: frozenset[CorporateActionType] = frozenset(),
    discontinuity_threshold: float = 0.35,
    action_window_days: int = 3,
) -> CorporateActionEvidenceReport:
    """Check scope/identity and identify large moves near known actions.

    A nearby corporate action is evidence that a discontinuity deserves action-aware review; it is
    not proof that the action caused the move and this function never adjusts or repairs prices.
    """

    if end < start:
        raise ValueError("corporate-action evidence end must be on or after start")
    if discontinuity_threshold <= 0:
        raise ValueError("discontinuity threshold must be positive")
    if action_window_days < 0:
        raise ValueError("action window days must be non-negative")

    action_records = tuple(actions)
    bar_records = tuple(bars)
    wrong_provider_actions = tuple(
        item for item in action_records if item.provider_id != provider_id
    )
    wrong_provider_bars = tuple(item for item in bar_records if item.provider_id != provider_id)
    out_of_range_actions = tuple(
        item for item in action_records if not start <= item.effective_date <= end
    )
    out_of_range_bars = tuple(item for item in bar_records if not start <= item.trade_date <= end)
    observed_types = frozenset(item.action_type for item in action_records)
    missing_types = expected_action_types - observed_types

    checks = (
        _check("action_provider_scope", not wrong_provider_actions, len(wrong_provider_actions)),
        _check("bar_provider_scope", not wrong_provider_bars, len(wrong_provider_bars)),
        _check("action_date_scope", not out_of_range_actions, len(out_of_range_actions)),
        _check("bar_date_scope", not out_of_range_bars, len(out_of_range_bars)),
        CorporateActionEvidenceCheck(
            check_id="expected_action_types",
            state=_state(not missing_types),
            detail=(
                "missing=" + ",".join(sorted(item.value for item in missing_types))
                if missing_types
                else "all configured action types observed"
            ),
        ),
    )

    return CorporateActionEvidenceReport(
        provider_id=provider_id,
        checks=checks,
        discontinuities=_find_discontinuities(
            bar_records,
            action_records,
            threshold=discontinuity_threshold,
            action_window_days=action_window_days,
        ),
    )


def _find_discontinuities(
    bars: tuple[ProviderDailyBar, ...],
    actions: tuple[ProviderCorporateAction, ...],
    *,
    threshold: float,
    action_window_days: int,
) -> tuple[PriceDiscontinuity, ...]:
    by_instrument: dict[str, list[ProviderDailyBar]] = {}
    for bar in bars:
        by_instrument.setdefault(bar.provider_instrument_id, []).append(bar)

    result: list[PriceDiscontinuity] = []
    window = timedelta(days=action_window_days)
    for provider_instrument_id, instrument_bars in by_instrument.items():
        ordered = sorted(instrument_bars, key=lambda item: item.trade_date)
        for previous, current in pairwise(ordered):
            if previous.close == 0:
                continue
            change = current.close / previous.close - 1.0
            if abs(change) < threshold:
                continue
            nearby = tuple(
                sorted(
                    {
                        action.action_type
                        for action in actions
                        if action.provider_instrument_id == provider_instrument_id
                        and previous.trade_date - window
                        <= action.effective_date
                        <= current.trade_date + window
                    },
                    key=lambda item: item.value,
                )
            )
            result.append(
                PriceDiscontinuity(
                    provider_instrument_id=provider_instrument_id,
                    previous_date=previous.trade_date,
                    trade_date=current.trade_date,
                    return_fraction=change,
                    nearby_action_types=nearby,
                )
            )
    return tuple(sorted(result, key=lambda item: (item.provider_instrument_id, item.trade_date)))


def _check(check_id: str, condition: bool, count: int) -> CorporateActionEvidenceCheck:
    return CorporateActionEvidenceCheck(
        check_id=check_id,
        state=_state(condition),
        detail=f"violation_count={count}",
    )


def _state(condition: bool) -> CorporateActionEvidenceState:
    return CorporateActionEvidenceState.PASS if condition else CorporateActionEvidenceState.FAIL
