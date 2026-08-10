import pytest

from trade_scout.api.dashboard_architecture import (
    ChartKind,
    ControlBinding,
    ControlBindingKind,
    DashboardBlueprint,
    NavigationItem,
    WorkspaceBlueprint,
    WorkspaceId,
    default_dashboard_blueprint,
)


def test_default_blueprint_has_exact_primary_workspaces() -> None:
    blueprint = default_dashboard_blueprint()

    assert tuple(item.workspace_id for item in blueprint.workspaces) == (
        WorkspaceId.RESEARCH,
        WorkspaceId.SCANNER,
        WorkspaceId.CANDIDATE,
        WorkspaceId.EXPERIMENTS,
        WorkspaceId.DATA_HEALTH,
        WorkspaceId.ALERTS,
        WorkspaceId.SYSTEM,
    )
    assert tuple(item.workspace_id for item in blueprint.navigation) == tuple(
        item.workspace_id for item in blueprint.workspaces
    )


def test_research_controls_bind_to_validated_configuration() -> None:
    research = default_dashboard_blueprint().workspace(WorkspaceId.RESEARCH)

    assert research.controls
    assert all(item.kind is ControlBindingKind.ANALYTICAL_CONFIG for item in research.controls)
    assert all(item.source_path.startswith("config.") for item in research.controls)
    assert all(item.requires_resolved_configuration_review for item in research.controls)


def test_scanner_controls_are_display_only() -> None:
    scanner = default_dashboard_blueprint().workspace(WorkspaceId.SCANNER)

    assert scanner.controls
    assert all(item.kind is ControlBindingKind.DISPLAY_STATE for item in scanner.controls)
    assert all(item.source_path.startswith("ui.") for item in scanner.controls)
    assert not any(item.requires_resolved_configuration_review for item in scanner.controls)


def test_candidate_price_chart_requires_canonical_price_basis() -> None:
    candidate = default_dashboard_blueprint().workspace(WorkspaceId.CANDIDATE)
    price_chart = next(
        item for item in candidate.charts if item.chart_id == "candidate-price-context"
    )

    assert price_chart.kind is ChartKind.CANDLESTICK
    assert price_chart.canonical_price_basis_required is True
    assert price_chart.provenance_required is True
    assert {"open", "high", "low", "close", "volume"}.issubset(price_chart.required_fields)


def test_dashboard_workspaces_prohibit_embedded_analytical_logic() -> None:
    blueprint = default_dashboard_blueprint()

    assert not any(item.analytical_logic_allowed for item in blueprint.workspaces)
    assert all(item.provenance_panel_required for item in blueprint.workspaces)


def test_analytical_control_without_config_binding_fails_closed() -> None:
    with pytest.raises(ValueError, match="config"):
        ControlBinding(
            control_id="bad",
            label="Bad analytical control",
            kind=ControlBindingKind.ANALYTICAL_CONFIG,
            source_path="ui.bad",
            requires_resolved_configuration_review=True,
        )


def test_display_control_cannot_claim_resolved_config_review() -> None:
    with pytest.raises(ValueError, match="display-only"):
        ControlBinding(
            control_id="bad-display",
            label="Bad display control",
            kind=ControlBindingKind.DISPLAY_STATE,
            source_path="ui.scanner.bad",
            requires_resolved_configuration_review=True,
        )


def test_blueprint_rejects_duplicate_workspace_routes() -> None:
    workspace = WorkspaceBlueprint(
        workspace_id=WorkspaceId.RESEARCH,
        title="Research",
        route="/same",
        purpose="test purpose",
        primary_questions=("question",),
        required_contracts=("Contract",),
        controls=(),
        charts=(),
        provenance_panel_required=True,
    )
    other = WorkspaceBlueprint(
        workspace_id=WorkspaceId.SCANNER,
        title="Scanner",
        route="/same",
        purpose="test purpose",
        primary_questions=("question",),
        required_contracts=("Contract",),
        controls=(),
        charts=(),
        provenance_panel_required=True,
    )
    navigation = (
        NavigationItem(WorkspaceId.RESEARCH, "Research", "/same", "test"),
        NavigationItem(WorkspaceId.SCANNER, "Scanner", "/same", "test"),
    )

    with pytest.raises(ValueError, match="routes"):
        DashboardBlueprint(version="test", navigation=navigation, workspaces=(workspace, other))
