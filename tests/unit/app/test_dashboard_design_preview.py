from trade_scout.api.dashboard_architecture import default_dashboard_blueprint
from trade_scout.app.dashboard_design_preview import (
    ScannerDisplayFilter,
    filter_scanner_candidates,
    render_dashboard_design_preview,
    synthetic_scanner_candidates,
)


def test_display_filter_changes_visible_rows_without_mutating_candidates() -> None:
    candidates = synthetic_scanner_candidates()
    original = candidates

    visible = filter_scanner_candidates(
        candidates,
        ScannerDisplayFilter(candidate_states=("TRIGGER_READY",)),
    )

    assert candidates == original
    assert len(visible) == 1
    assert visible[0] is candidates[0]
    assert visible[0].symbol == "ALFA"


def test_display_filter_can_search_symbol_or_company_name() -> None:
    candidates = synthetic_scanner_candidates()

    by_symbol = filter_scanner_candidates(candidates, ScannerDisplayFilter(search_text="beta"))
    by_company = filter_scanner_candidates(
        candidates, ScannerDisplayFilter(search_text="gamma holdings")
    )

    assert tuple(item.symbol for item in by_symbol) == ("BETA",)
    assert tuple(item.symbol for item in by_company) == ("GAMM",)


def test_preview_exposes_primary_workspaces_and_chart_contracts() -> None:
    html = render_dashboard_design_preview(default_dashboard_blueprint())

    for label in (
        "Research Lab",
        "Market Scanner",
        "Candidate Detail",
        "Experiment Library",
        "Data Health",
        "Alerts",
        "System / Project",
    ):
        assert label in html
    for chart_id in (
        "forward-return-distribution",
        "parameter-surface",
        "parameter-sample-size",
        "candidate-price-context",
        "candidate-mae-mfe",
        "candidate-outcomes",
        "experiment-fold-performance",
        "data-health-timeline",
    ):
        assert chart_id in html


def test_preview_labels_analytical_and_display_state_boundaries() -> None:
    html = render_dashboard_design_preview()

    assert "ANALYTICAL_CONFIG" in html
    assert "DISPLAY_STATE" in html
    assert "config.data.dataset_version" in html
    assert "ui.scanner.candidate_state" in html
    assert "No analytical logic lives here." in html


def test_preview_filter_only_changes_rendered_scanner_subset() -> None:
    html = render_dashboard_design_preview(
        scanner_filter=ScannerDisplayFilter(candidate_states=("QUALIFIED",))
    )

    assert "Showing 1 of 3 synthetic candidates" in html
    assert "Synthetic Beta Industries" in html
    assert "Synthetic Alpha Corp" not in html
    assert "Synthetic Gamma Holdings" not in html


def test_preview_contains_no_trade_execution_controls() -> None:
    html = render_dashboard_design_preview()

    forbidden = ("Place order", "Buy now", "Sell now", "Execute trade", "Broker login")
    assert not any(label in html for label in forbidden)
    assert "No provider calls" in html
