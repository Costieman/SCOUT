from __future__ import annotations

import pytest

from trade_scout.app.universe_research_service import UniverseResearchRequest
from trade_scout.patterns.timeframes import PatternTimeframe


def test_encoded_strategy_query_resolves_pattern_timeframe() -> None:
    request = UniverseResearchRequest(strategy_id="consolidation_breakout@weekly")

    assert request.strategy_id == "consolidation_breakout"
    assert request.pattern_timeframe is PatternTimeframe.WEEKLY


def test_programmatic_request_can_set_pattern_timeframe_directly() -> None:
    request = UniverseResearchRequest(pattern_timeframe=PatternTimeframe.THREE_SESSION)

    assert request.pattern_timeframe is PatternTimeframe.THREE_SESSION


def test_unknown_encoded_timeframe_fails_closed() -> None:
    with pytest.raises(ValueError):
        UniverseResearchRequest(strategy_id="consolidation_breakout@monthly")
