from trade_scout.app import research_station_workflow_v7 as workflow
from trade_scout.app import research_workbench_console as console


def test_v7_identifies_and_focuses_invalid_control() -> None:
    source = workflow._RESEARCH_STATION_V7_JS
    assert 'form.addEventListener("invalid"' in source
    assert "fieldName" in source
    assert "sectionText" in source
    assert "Current value:" in source
    assert "Problem:" in source
    assert "Expected:" in source
    assert "research-invalid-focus" in source
    assert "scrollIntoView" in source
    assert "node.focus" in source


def test_v7_surfaces_custom_validator_reason_and_target() -> None:
    source = workflow._RESEARCH_STATION_V7_JS
    assert "customValidationSource" in source
    assert "enhanceCustomCancellation" in source
    assert 'document.getElementById("composer-error")' in source
    assert 'document.getElementById("sweep-preview")' in source
    assert "Strategy Builder validation failed" in source
    assert "SCOUT should never ask you to guess which parameter failed" in source
    assert "inferTarget" in source
    assert "profit target" in source
    assert "protective stop" in source
    assert "entry condition" in source


def test_v7_preserves_v5_suite_and_brain_runtime() -> None:
    workflow.configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Strategy suite" in asset
    assert "research-brain-session-card" in asset
    assert "+ New Brain" in asset
    assert "Run path: native-v5-validation-fix" in asset
    assert "research-validation-focus-style" in asset
    assert "customValidationSource" in asset
