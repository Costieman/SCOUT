from __future__ import annotations

from trade_scout.app.entry_strategy_registry import available_entry_strategies
from trade_scout.app.strategy_builder_surface import render_strategy_builder_html
from trade_scout.app.strategy_indicator_catalog import available_indicator_metrics
from trade_scout.app.visual_rule_builder import (
    RuleJoin,
    RuleOperator,
    VisualCondition,
    VisualRuleSet,
    recover_visual_conditions,
)
from trade_scout.statistics.strategy_research import available_strategy_features


def test_visual_rule_set_compiles_explicit_left_to_right_expression() -> None:
    conditions = (
        VisualCondition("return_20", RuleOperator.GREATER_THAN_OR_EQUAL, 0.05),
        VisualCondition(
            "relative_volume_20",
            RuleOperator.GREATER_THAN_OR_EQUAL,
            1.5,
            RuleJoin.AND,
        ),
        VisualCondition(
            "rsi_wilder_14",
            RuleOperator.LESS_THAN,
            45.0,
            RuleJoin.OR,
        ),
    )

    expression = VisualRuleSet(conditions).expression

    assert expression == "((return_20 >= 0.05 and relative_volume_20 >= 1.5) or rsi_wilder_14 < 45)"
    assert recover_visual_conditions(expression) == conditions


def test_indicator_catalog_only_exposes_registered_strategy_features() -> None:
    registered = set(available_strategy_features())
    catalog = available_indicator_metrics()

    assert {item.feature_name for item in catalog} <= registered
    assert {item.indicator_id for item in catalog} >= {
        "macd",
        "moving_average",
        "rsi",
        "volume",
        "volatility",
        "breakout",
    }


def test_strategy_builder_surface_is_visual_composer_not_preset_menu() -> None:
    html = render_strategy_builder_html(
        universes=(),
        entries=available_entry_strategies(),
        features=available_strategy_features(),
    )

    assert "Visual Strategy Builder" in html
    assert "+ Add condition" in html
    assert "+ Add exit candidate" in html
    assert "0.01% to 99.99%" in html
    assert 'src="/assets/strategy-builder.js"' in html
    assert "Load an example hypothesis" in html
