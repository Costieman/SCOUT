"""Incremental lifecycle tracking for persistent consolidation pattern instances.

The tracker owns structural pattern state only. Breakout confirmation remains in the event layer,
which may explicitly consume the active instance after generating an event. Every update uses only
the bars and corporate actions supplied through that session.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from trade_scout.data.contracts import (
    CorporateActionRecord,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    _range_pct,
    _trend_qualified,
)
from trade_scout.patterns.consolidation_state import qualified_pattern_at
from trade_scout.patterns.contracts import PatternLifecycleState, PatternState


@dataclass(frozen=True, slots=True)
class ConsolidationLifecycleConfig:
    """Lifecycle policy layered on one registered consolidation definition."""

    trigger_ready_distance_pct: float = 0.02
    max_pattern_age_sessions: int | None = None
    reset_sessions: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.trigger_ready_distance_pct <= 1:
            raise ValueError("trigger_ready_distance_pct must be in [0, 1]")
        if self.max_pattern_age_sessions is not None and self.max_pattern_age_sessions < 1:
            raise ValueError("max_pattern_age_sessions must be positive when supplied")
        if not 0 <= self.reset_sessions <= 252:
            raise ValueError("reset_sessions must be between 0 and 252")


class ConsolidationPatternTracker:
    """Stateful point-in-time tracker for one instrument and one consolidation definition.

    A pattern instance begins when an exact prior window first qualifies. Its formation interval
    and structural boundaries then remain fixed until the instance is invalidated or explicitly
    consumed by the event layer. A later instance must be formed wholly after the terminal session,
    preventing a rolling window from silently reusing the same structural episode.
    """

    def __init__(
        self,
        pattern_config: ConsolidationBreakoutConfig,
        lifecycle_config: ConsolidationLifecycleConfig | None = None,
    ) -> None:
        self.pattern_config = pattern_config
        self.lifecycle_config = lifecycle_config or ConsolidationLifecycleConfig(
            reset_sessions=pattern_config.cooldown_sessions
        )
        self._bars: list[ResearchBar] = []
        self._active: PatternState | None = None
        self._active_start_index: int | None = None
        self._active_end_index: int | None = None
        self._last_terminal_index: int | None = None
        self._last_terminal_date: date | None = None
        self._instrument_id: InstrumentId | None = None
        self._dataset_version: str | None = None
        self._representation: PriceRepresentation | None = None

    @property
    def bars(self) -> tuple[ResearchBar, ...]:
        """Return the exact point-in-time history observed by this tracker."""

        return tuple(self._bars)

    @property
    def active_pattern(self) -> PatternState | None:
        """Return the current non-terminal pattern snapshot, when one exists."""

        return self._active

    def update(
        self,
        bar: ResearchBar,
        *,
        corporate_actions: tuple[CorporateActionRecord, ...] = (),
    ) -> PatternState | None:
        """Advance one session without inspecting any future bar or outcome."""

        self._validate_next_bar(bar)
        self._validate_actions(bar, corporate_actions)
        self._bars.append(bar)
        signal_index = len(self._bars) - 1

        if self._active is not None:
            invalidation_reason = self._invalidation_reason(
                bar,
                signal_index=signal_index,
                corporate_actions=corporate_actions,
            )
            if invalidation_reason is not None:
                return self._invalidate(bar, signal_index, invalidation_reason)
            return self._snapshot_active(bar)

        if corporate_actions:
            self._record_terminal(signal_index, bar.trade_date)
            return None
        if signal_index < self.pattern_config.duration:
            return None

        candidate = qualified_pattern_at(
            tuple(self._bars),
            signal_index=signal_index,
            config=self.pattern_config,
        )
        if candidate is None or not self._eligible_after_reset(candidate, signal_index):
            return None

        self._active = candidate
        self._active_start_index = self._index_for_date(candidate.formation_start)
        self._active_end_index = self._index_for_date(candidate.formation_end)
        return self._snapshot_active(bar)

    def consume(self, bar: ResearchBar) -> PatternState:
        """Close the current instance after the event layer has emitted its event."""

        if self._active is None:
            raise ValueError("cannot consume a consolidation pattern when none is active")
        if not self._bars or self._bars[-1].trade_date != bar.trade_date:
            raise ValueError("consume must reference the most recently observed bar")

        consumed = replace(
            self._active,
            as_of_date=bar.trade_date,
            state=PatternLifecycleState.CONSUMED,
        )
        self._record_terminal(len(self._bars) - 1, bar.trade_date)
        self._clear_active()
        return consumed

    def _validate_next_bar(self, bar: ResearchBar) -> None:
        if self._bars and bar.trade_date <= self._bars[-1].trade_date:
            raise ValueError("incremental pattern bars must be unique and date-increasing")
        if self._instrument_id is None:
            self._instrument_id = bar.instrument_id
            self._dataset_version = str(bar.dataset_version)
            self._representation = bar.price_representation
            return
        if bar.instrument_id != self._instrument_id:
            raise ValueError("incremental pattern tracking requires one instrument")
        if str(bar.dataset_version) != self._dataset_version:
            raise ValueError("incremental pattern tracking requires one dataset version")
        if bar.price_representation is not self._representation:
            raise ValueError("incremental pattern tracking cannot mix price representations")

    @staticmethod
    def _validate_actions(
        bar: ResearchBar,
        corporate_actions: tuple[CorporateActionRecord, ...],
    ) -> None:
        for action in corporate_actions:
            if action.instrument_id != bar.instrument_id:
                raise ValueError("corporate action and bar must reference the same instrument")
            if action.effective_date != bar.trade_date:
                raise ValueError("incremental corporate actions must match the current bar date")

    def _eligible_after_reset(self, candidate: PatternState, signal_index: int) -> bool:
        if self._last_terminal_index is None or self._last_terminal_date is None:
            return True
        sessions_since_terminal = signal_index - self._last_terminal_index
        if sessions_since_terminal <= self.lifecycle_config.reset_sessions:
            return False
        return candidate.formation_start > self._last_terminal_date

    def _invalidation_reason(
        self,
        bar: ResearchBar,
        *,
        signal_index: int,
        corporate_actions: tuple[CorporateActionRecord, ...],
    ) -> str | None:
        if corporate_actions:
            return "corporate_action_discontinuity"
        if not bar.eligibility or bar.quality_status is not QualityStatus.PASS:
            return "data_quality_or_eligibility"
        if not _trend_qualified(tuple(self._bars), signal_index, self.pattern_config.trend_filter):
            return "trend_context_failed"

        active = self._require_active()
        support = active.structural_boundaries["support"]
        resistance = active.structural_boundaries["resistance"]
        if bar.close < support:
            return "closed_below_support"
        if self.lifecycle_config.max_pattern_age_sessions is not None:
            active_end_index = self._require_active_end_index()
            age_sessions = signal_index - active_end_index
            if age_sessions > self.lifecycle_config.max_pattern_age_sessions:
                return "maximum_age_exceeded"

        if bar.close <= resistance and self._episode_range_exceeded(signal_index):
            return "range_expanded_beyond_limit"
        return None

    def _episode_range_exceeded(self, signal_index: int) -> bool:
        active = self._require_active()
        active_start_index = self._require_active_start_index()
        episode = self._bars[active_start_index : signal_index + 1]
        high = max(active.structural_boundaries["resistance"], *(bar.high for bar in episode))
        low = min(active.structural_boundaries["support"], *(bar.low for bar in episode))
        return _range_pct(high, low) > self.pattern_config.max_range_pct

    def _snapshot_active(self, bar: ResearchBar) -> PatternState:
        active = self._require_active()
        resistance = active.structural_boundaries["resistance"]
        distance = (resistance - bar.close) / resistance
        state = PatternLifecycleState.QUALIFIED
        if 0 <= distance <= self.lifecycle_config.trigger_ready_distance_pct:
            state = PatternLifecycleState.TRIGGER_READY
        snapshot = replace(active, as_of_date=bar.trade_date, state=state)
        self._active = snapshot
        return snapshot

    def _invalidate(self, bar: ResearchBar, signal_index: int, reason: str) -> PatternState:
        active = self._require_active()
        parameters = dict(active.resolved_parameters)
        parameters["invalidation_reason"] = reason
        invalidated = replace(
            active,
            as_of_date=bar.trade_date,
            state=PatternLifecycleState.INVALIDATED,
            resolved_parameters=parameters,
        )
        self._record_terminal(signal_index, bar.trade_date)
        self._clear_active()
        return invalidated

    def _index_for_date(self, target: date) -> int:
        for index, bar in enumerate(self._bars):
            if bar.trade_date == target:
                return index
        raise ValueError(
            f"pattern formation date {target.isoformat()} is absent from observed bars"
        )

    def _record_terminal(self, index: int, terminal_date: date) -> None:
        self._last_terminal_index = index
        self._last_terminal_date = terminal_date

    def _clear_active(self) -> None:
        self._active = None
        self._active_start_index = None
        self._active_end_index = None

    def _require_active(self) -> PatternState:
        if self._active is None:
            raise RuntimeError("active consolidation pattern is unexpectedly absent")
        return self._active

    def _require_active_start_index(self) -> int:
        if self._active_start_index is None:
            raise RuntimeError("active consolidation start index is unexpectedly absent")
        return self._active_start_index

    def _require_active_end_index(self) -> int:
        if self._active_end_index is None:
            raise RuntimeError("active consolidation end index is unexpectedly absent")
        return self._active_end_index
