"""Evidence model for characterizing Stooq coverage of inactive or delisted securities.

The model is intentionally descriptive. Caller-supplied lifecycle facts must come from an
independently reviewed source. Stooq observations are compared with those facts without inferring
that absence means delisting, without inventing terminal returns, and without promoting Stooq to a
canonical provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from collections.abc import Sequence

from trade_scout.data.provider import ProviderDailyBar


class StooqInactiveEvidenceState(StrEnum):
    """Observed Stooq behavior for one externally identified inactive security."""

    HISTORY_PRESENT_TERMINAL_ALIGNED = "HISTORY_PRESENT_TERMINAL_ALIGNED"
    HISTORY_PRESENT_TERMINAL_MISMATCH = "HISTORY_PRESENT_TERMINAL_MISMATCH"
    NO_HISTORY = "NO_HISTORY"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class StooqInactiveEvidence:
    """Auditable comparison between Stooq history and an external inactive-security fact."""

    symbol: str
    expected_terminal_date: date | None
    observation_count: int
    first_trade_date: date | None
    last_trade_date: date | None
    terminal_date_error_days: int | None
    state: StooqInactiveEvidenceState
    note: str


def characterize_stooq_inactive_history(
    bars: Sequence[ProviderDailyBar],
    *,
    symbol: str,
    expected_terminal_date: date | None,
    terminal_tolerance_days: int = 10,
) -> StooqInactiveEvidence:
    """Characterize historical availability for one externally verified inactive security.

    ``expected_terminal_date`` is optional because some independent references identify an inactive
    security without supplying a sufficiently precise final trading date. In that case, presence of
    history is useful evidence but remains ``INCONCLUSIVE`` about terminal-date fidelity.
    """

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Stooq inactive evidence symbol must be non-empty")
    if terminal_tolerance_days < 0:
        raise ValueError("terminal_tolerance_days must be non-negative")

    scoped = tuple(
        sorted(
            (
                bar
                for bar in bars
                if bar.provider_id == "stooq" and bar.symbol.upper() == normalized_symbol
            ),
            key=lambda bar: bar.trade_date,
        )
    )
    if not scoped:
        return StooqInactiveEvidence(
            symbol=normalized_symbol,
            expected_terminal_date=expected_terminal_date,
            observation_count=0,
            first_trade_date=None,
            last_trade_date=None,
            terminal_date_error_days=None,
            state=StooqInactiveEvidenceState.NO_HISTORY,
            note=(
                "Stooq returned no observations for the supplied inactive-security query. This is "
                "evidence of absent coverage for this query only; it does not prove why data are "
                "absent."
            ),
        )

    first_date = scoped[0].trade_date
    last_date = scoped[-1].trade_date
    if expected_terminal_date is None:
        return StooqInactiveEvidence(
            symbol=normalized_symbol,
            expected_terminal_date=None,
            observation_count=len(scoped),
            first_trade_date=first_date,
            last_trade_date=last_date,
            terminal_date_error_days=None,
            state=StooqInactiveEvidenceState.INCONCLUSIVE,
            note=(
                "Historical observations are present, but no independently verified terminal date "
                "was supplied, so terminal-date fidelity cannot be assessed."
            ),
        )

    error_days = abs((last_date - expected_terminal_date).days)
    aligned = error_days <= terminal_tolerance_days
    state = (
        StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_ALIGNED
        if aligned
        else StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_MISMATCH
    )
    note = (
        "Stooq history is present and its final observation is within the configured tolerance of "
        "the independently supplied terminal date."
        if aligned
        else "Stooq history is present, but its final observation is outside the configured "
        "tolerance of the independently supplied terminal date."
    )
    return StooqInactiveEvidence(
        symbol=normalized_symbol,
        expected_terminal_date=expected_terminal_date,
        observation_count=len(scoped),
        first_trade_date=first_date,
        last_trade_date=last_date,
        terminal_date_error_days=error_days,
        state=state,
        note=note,
    )
