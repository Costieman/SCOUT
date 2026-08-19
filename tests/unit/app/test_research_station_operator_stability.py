from trade_scout.app import research_station_workflow_v5 as workflow
from trade_scout.app import research_workbench_console as console
from trade_scout.app import strategy_builder_surface as surface


def test_research_station_operator_path_stays_integrated() -> None:
    """Guard the operator-critical Suite -> Brain -> Run path as one runtime asset."""

    workflow.configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS

    assert "Strategy suite" in asset
    assert "Suite loaded — not run." in asset
    assert "research-brain-session-card" in asset
    assert 'fetch("/research/brains"' in asset
    assert "+ New Brain" in asset
    assert "Run path: native-v5-validation-fix" in asset
    assert "form.reportValidity()" in asset
    assert "form.requestSubmit()" in asset
    assert "Research did not start" in asset
    assert 'statusText.startsWith("Request accepted")' in asset


def test_successful_run_handoff_is_not_reported_as_validation_failure() -> None:
    source = workflow._RESEARCH_STATION_V5_JS
    assert 'statusText.startsWith("Request accepted")' in source
    assert "intentional handoff is success" in source
    assert "event.defaultPrevented" in source


def test_completed_report_keeps_stability_evidence_visible() -> None:
    """Keep provenance/performance evidence visible in every completed report."""

    literals = "\n".join(
        item for item in surface._render_report.__code__.co_consts if isinstance(item, str)
    )
    assert "Frozen entry definition" in literals
    assert "Dataset" in literals
    assert "Provider calls" in literals
    assert "Run performance" in literals
    assert "Canonical daily bars loaded" in literals
    assert "Daily bars actually analyzed" in literals
    assert "Interpretation boundary" in literals
