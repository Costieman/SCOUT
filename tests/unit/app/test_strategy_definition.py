from __future__ import annotations

import pytest

from trade_scout.app.strategy_definition import (
    LOW_VOL_TREND,
    MOMENTUM_RVOL_TREND,
    STRATEGY_LIBRARY,
    StrategyDefinition,
)


def test_strategy_definition_materializes_scanner_request() -> None:
    request = MOMENTUM_RVOL_TREND.scanner_request()

    assert request.expression == MOMENTUM_RVOL_TREND.expression
    assert request.sort_by == "return_20"
    assert request.descending is True
    assert request.limit == 100


def test_strategy_library_has_unique_ids() -> None:
    ids = [item.strategy_id for item in STRATEGY_LIBRARY]

    assert len(ids) == len(set(ids))
    assert LOW_VOL_TREND in STRATEGY_LIBRARY
    assert MOMENTUM_RVOL_TREND in STRATEGY_LIBRARY


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strategy_id", ""),
        ("name", ""),
        ("description", ""),
        ("expression", ""),
    ],
)
def test_strategy_definition_rejects_blank_required_fields(field: str, value: str) -> None:
    values = {
        "strategy_id": "test-v0.1",
        "name": "Test",
        "description": "Synthetic strategy definition.",
        "expression": "return_20 > 0",
    }
    values[field] = value

    with pytest.raises(ValueError):
        StrategyDefinition(**values)


def test_strategy_definition_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        StrategyDefinition(
            strategy_id="test-v0.1",
            name="Test",
            description="Synthetic strategy definition.",
            expression="return_20 > 0",
            limit=0,
        )
