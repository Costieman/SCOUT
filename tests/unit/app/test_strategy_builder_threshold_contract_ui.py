from trade_scout.app import research_workbench_console as console
from trade_scout.app import strategy_builder_threshold_contract_ui as threshold_ui


def test_threshold_contract_repair_uses_static_catalog_metadata(monkeypatch) -> None:
    monkeypatch.setattr(console, "STRATEGY_BUILDER_RESEARCH_MEMORY_JS", "base-asset")
    monkeypatch.setattr(threshold_ui, "_CONFIGURED", False)

    threshold_ui.configure_threshold_contract_ui()

    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "thresholdContractObserver" in asset
    assert 'row.querySelector(".rule-indicator")?.value !== "legacy_fixed"' in asset
    assert "meta.min_value" in asset
    assert "meta.max_value" in asset
    assert "meta.step" in asset


def test_threshold_contract_repair_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(console, "STRATEGY_BUILDER_RESEARCH_MEMORY_JS", "base-asset")
    monkeypatch.setattr(threshold_ui, "_CONFIGURED", False)

    threshold_ui.configure_threshold_contract_ui()
    once = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    threshold_ui.configure_threshold_contract_ui()

    assert once == console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
