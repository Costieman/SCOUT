from __future__ import annotations

from trade_scout.app.strategy_presets import available_strategy_presets, strategy_preset
from trade_scout.statistics.strategy_research import available_strategy_features


def test_strategy_presets_are_unique_and_use_registered_features() -> None:
    presets = available_strategy_presets()
    feature_names = set(available_strategy_features())

    assert len(presets) >= 6
    assert len({item.preset_id for item in presets}) == len(presets)
    assert all(item.rank_feature in feature_names for item in presets)
    assert all(item.expression.strip() for item in presets)


def test_strategy_preset_resolves_to_existing_strategy_definition_contract() -> None:
    preset = strategy_preset("macd_bullish_cross_in_uptrend")
    definition = preset.definition()

    assert definition.strategy_id == "preset:macd_bullish_cross_in_uptrend"
    assert definition.expression == preset.expression
    assert definition.rank_feature == preset.rank_feature
    assert definition.descending is True
    assert definition.per_session_limit == preset.per_session_limit
