from __future__ import annotations

from trade_scout.app import research_workbench_console as console
from trade_scout.app.research_station_integration import configure_research_station_runtime


def test_runtime_enables_same_origin_brain_discovery() -> None:
    configure_research_station_runtime()
    assert "connect-src 'self'" in console._csp_value()


def test_suite_loader_is_configuration_only() -> None:
    configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Suite loaded — not run." in asset
    assert "setControl(form, name, value)" in asset
    assert 'history.replaceState({}, "", url.pathname + url.search)' in asset
    assert "window.location.assign(suiteLaunchUrl(suite))" in asset
    assert "oldButton.cloneNode(true)" in asset


def test_brains_are_available_and_creatable_inside_research_station() -> None:
    configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert 'fetch("/research/brains"' in asset
    assert 'create.textContent = "+ New Brain"' in asset
    assert 'action: "create"' in asset
    assert "repopulateBrainSelect(select, status)" in asset


def test_completed_run_is_automatically_associated_with_active_brain() -> None:
    configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "autoAssociateRun" in asset
    assert 'action: "add"' in asset
    assert 'actor: "research-station"' in asset
    assert "Automatically associated by the active Research Station Brain context." in asset


def test_duplicate_detection_uses_complete_editable_research_form() -> None:
    configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "completeFormFingerprint" in asset
    assert "new FormData(form).entries()" in asset
    assert "last_run_form_fingerprint" in asset
    assert "including horizons, stops, targets, filters, and added research variables" in asset
    assert 'form.addEventListener("input", refreshAccurateDuplicateNotice)' in asset
    assert 'form.addEventListener("change", refreshAccurateDuplicateNotice)' in asset


def test_duplicate_warning_can_be_explicitly_ignored() -> None:
    configure_research_station_runtime()
    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "Ignore warning — continue anyway" in asset
    assert "duplicateDismissalKey" in asset
    assert "sessionStorage.setItem(duplicateDismissalKey(brain, fingerprint), \"1\")" in asset
