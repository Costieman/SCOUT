from __future__ import annotations

import pytest

from trade_scout.app.exit_policy_lab_service import (
    ExitPolicyLabRequest,
    parse_multiple_grid,
    parse_percentage_grid,
)


def test_percentage_grid_parses_operator_percent_points() -> None:
    assert parse_percentage_grid("2,3,5,7.5") == (0.02, 0.03, 0.05, 0.075)
    assert parse_percentage_grid("") == ()


def test_multiple_grid_accepts_empty_family_and_decimal_multiples() -> None:
    assert parse_multiple_grid("1,1.5,2.25") == (1.0, 1.5, 2.25)
    assert parse_multiple_grid("") == ()


def test_request_allows_operator_to_exclude_or_customize_policy_families() -> None:
    request = ExitPolicyLabRequest(
        fixed_percentages=(0.02,),
        atr_multiples=(),
        trailing_percentages=(0.025, 0.05),
        trailing_atr_multiples=(),
    )

    assert request.fixed_percentages == (0.02,)
    assert request.atr_multiples == ()
    assert request.trailing_percentages == (0.025, 0.05)


def test_percentage_grid_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        parse_percentage_grid("2,0,5")
    with pytest.raises(ValueError, match="below 100"):
        parse_percentage_grid("100")
