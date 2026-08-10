"""Versioned presentation architecture for the Trade Scout dashboard.

The objects in this module describe what the user interface is allowed to render and which
application/API contracts it consumes. They deliberately contain no market-data retrieval,
feature, pattern, event, outcome, risk, statistics, or ranking calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkspaceId(StrEnum):
    """Stable user-workspace identifiers independent of front-end framework."""

    RESEARCH = "research"
    SCANNER = "scanner"
    CANDIDATE = "candidate"
    EXPERIMENTS = "experiments"
    DATA_HEALTH = "data-health"
    ALERTS = "alerts"
    SYSTEM = "system"


class ChartKind(StrEnum):
    """Presentation-level chart families supported by the Version 1 blueprint."""

    CANDLESTICK = "CANDLESTICK"
    DISTRIBUTION = "DISTRIBUTION"
    HORIZON_SERIES = "HORIZON_SERIES"
    HEATMAP = "HEATMAP"
    SCATTER = "SCATTER"
    BAR = "BAR"
    STATUS_TIMELINE = "STATUS_TIMELINE"


class ControlBindingKind(StrEnum):
    """Whether a UI control changes analytical configuration or display state only."""

    ANALYTICAL_CONFIG = "ANALYTICAL_CONFIG"
    DISPLAY_STATE = "DISPLAY_STATE"


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """One stable primary-navigation entry."""

    workspace_id: WorkspaceId
    label: str
    route: str
    description: str

    def __post_init__(self) -> None:
        if not self.label.strip() or not self.description.strip():
            raise ValueError("navigation labels and descriptions must be non-empty")
        if not self.route.startswith("/"):
            raise ValueError("dashboard routes must be absolute application routes")


@dataclass(frozen=True, slots=True)
class ControlBinding:
    """Source-of-truth contract for one user-editable control.

    Analytical controls bind to a validated configuration path and therefore require resolved
    configuration review before launch. Display-state controls may change presentation only.
    """

    control_id: str
    label: str
    kind: ControlBindingKind
    source_path: str
    requires_resolved_configuration_review: bool

    def __post_init__(self) -> None:
        if not self.control_id.strip() or not self.label.strip() or not self.source_path.strip():
            raise ValueError("control binding fields must be non-empty")
        if self.kind is ControlBindingKind.ANALYTICAL_CONFIG:
            if not self.source_path.startswith("config."):
                raise ValueError("analytical controls must bind to validated config.* paths")
            if not self.requires_resolved_configuration_review:
                raise ValueError("analytical controls require resolved configuration review")
        elif self.requires_resolved_configuration_review:
            raise ValueError("display-only controls must not require analytical config review")


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Framework-neutral chart contract consuming already-computed application data."""

    chart_id: str
    title: str
    kind: ChartKind
    source_contract: str
    required_fields: tuple[str, ...]
    x_semantics: str
    y_semantics: str
    empty_state_message: str
    provenance_required: bool = True
    canonical_price_basis_required: bool = False

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.chart_id,
                self.title,
                self.source_contract,
                self.x_semantics,
                self.y_semantics,
                self.empty_state_message,
            )
        ):
            raise ValueError("chart specification text fields must be non-empty")
        if not self.required_fields or any(not field.strip() for field in self.required_fields):
            raise ValueError("chart specifications require explicit source fields")


@dataclass(frozen=True, slots=True)
class WorkspaceBlueprint:
    """Contract and wireframe requirements for one primary user workspace."""

    workspace_id: WorkspaceId
    title: str
    route: str
    purpose: str
    primary_questions: tuple[str, ...]
    required_contracts: tuple[str, ...]
    controls: tuple[ControlBinding, ...]
    charts: tuple[ChartSpec, ...]
    provenance_panel_required: bool
    analytical_logic_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.purpose.strip():
            raise ValueError("workspace title and purpose must be non-empty")
        if not self.route.startswith("/"):
            raise ValueError("workspace routes must be absolute")
        if not self.primary_questions or not self.required_contracts:
            raise ValueError("workspace blueprint requires questions and source contracts")
        if self.analytical_logic_allowed:
            raise ValueError("dashboard workspaces may not contain analytical logic")
        control_ids = [item.control_id for item in self.controls]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("workspace control IDs must be unique")
        chart_ids = [item.chart_id for item in self.charts]
        if len(chart_ids) != len(set(chart_ids)):
            raise ValueError("workspace chart IDs must be unique")


@dataclass(frozen=True, slots=True)
class DashboardBlueprint:
    """Complete versioned application-navigation and visualization blueprint."""

    version: str
    navigation: tuple[NavigationItem, ...]
    workspaces: tuple[WorkspaceBlueprint, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("dashboard blueprint version must be non-empty")
        workspace_ids = [item.workspace_id for item in self.workspaces]
        routes = [item.route for item in self.workspaces]
        if len(workspace_ids) != len(set(workspace_ids)):
            raise ValueError("dashboard workspace IDs must be unique")
        if len(routes) != len(set(routes)):
            raise ValueError("dashboard workspace routes must be unique")
        workspace_by_id = {item.workspace_id: item for item in self.workspaces}
        if {item.workspace_id for item in self.navigation} != set(workspace_by_id):
            raise ValueError("primary navigation must cover each workspace exactly once")
        for item in self.navigation:
            if item.route != workspace_by_id[item.workspace_id].route:
                raise ValueError("navigation route does not match workspace route")

    def workspace(self, workspace_id: WorkspaceId) -> WorkspaceBlueprint:
        """Return one workspace definition by stable identifier."""

        for item in self.workspaces:
            if item.workspace_id is workspace_id:
                return item
        raise KeyError(workspace_id)


def default_dashboard_blueprint() -> DashboardBlueprint:
    """Return the Version 0.2 design blueprint derived from the accepted UI specification."""

    workspaces = (
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.RESEARCH,
            title="Research Lab",
            route="/research",
            purpose=(
                "Configure and inspect reproducible experiments without placing analytical logic "
                "inside the presentation layer."
            ),
            primary_questions=(
                "What hypothesis and configuration are being tested?",
                "What does the full distribution of evidence look like?",
                "Is an apparent result broad and robust rather than an isolated optimum?",
            ),
            required_contracts=(
                "ResearchLabSummary",
                "ResolvedExperimentConfiguration",
                "ExperimentResultsView",
                "ProvenanceSummary",
            ),
            controls=(
                _analytical_control("strategy-family", "Strategy family", "config.patterns.family"),
                _analytical_control("dataset-version", "Dataset", "config.data.dataset_version"),
                _analytical_control("universe", "Universe", "config.universe"),
                _analytical_control(
                    "outcome-horizons", "Outcome horizons", "config.outcomes.horizons"
                ),
                _analytical_control("risk-policy", "Risk policy", "config.risk.policy"),
                _analytical_control("validation-design", "Validation design", "config.validation"),
            ),
            charts=(
                ChartSpec(
                    chart_id="forward-return-distribution",
                    title="Forward-return distribution",
                    kind=ChartKind.DISTRIBUTION,
                    source_contract="ExperimentResultsView",
                    required_fields=("horizon", "return_distribution", "sample_count"),
                    x_semantics="forward return",
                    y_semantics="frequency or density",
                    empty_state_message="No completed experiment outcome distribution is available.",
                ),
                ChartSpec(
                    chart_id="outcomes-by-horizon",
                    title="Outcome evidence by horizon",
                    kind=ChartKind.HORIZON_SERIES,
                    source_contract="ExperimentResultsView",
                    required_fields=(
                        "horizon",
                        "mean_return",
                        "median_return",
                        "positive_fraction",
                    ),
                    x_semantics="forward trading-session horizon",
                    y_semantics="already-computed outcome statistic",
                    empty_state_message="No horizon summary has been computed for this experiment.",
                ),
                ChartSpec(
                    chart_id="parameter-surface",
                    title="Parameter surface",
                    kind=ChartKind.HEATMAP,
                    source_contract="ParameterSurfaceView",
                    required_fields=("row_parameter", "column_parameter", "effect_value"),
                    x_semantics="registered parameter value",
                    y_semantics="registered parameter value",
                    empty_state_message="No parameter sweep is attached to this experiment.",
                ),
                ChartSpec(
                    chart_id="parameter-sample-size",
                    title="Parameter-cell sample size",
                    kind=ChartKind.HEATMAP,
                    source_contract="ParameterSurfaceView",
                    required_fields=("row_parameter", "column_parameter", "sample_count"),
                    x_semantics="registered parameter value",
                    y_semantics="registered parameter value",
                    empty_state_message="No parameter-cell sample sizes are available.",
                ),
            ),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.SCANNER,
            title="Market Scanner",
            route="/scanner",
            purpose="Display current validated setup states with freshness and historical evidence visible.",
            primary_questions=(
                "Which validated opportunities exist now?",
                "Which are triggered, trigger-ready, or merely qualified?",
                "Are freshness and evidence prerequisites satisfied?",
            ),
            required_contracts=("ScannerSummary", "ScannerCandidateSummary", "ProvenanceSummary"),
            controls=(
                _display_control(
                    "candidate-state", "Candidate state", "ui.scanner.candidate_state"
                ),
                _display_control("scanner-sort", "Sort candidates", "ui.scanner.sort"),
                _display_control("scanner-search", "Search", "ui.scanner.search"),
            ),
            charts=(),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.CANDIDATE,
            title="Candidate Detail",
            route="/candidate",
            purpose=(
                "Explain one current setup through chart context, comparable historical evidence, "
                "risk, and provenance."
            ),
            primary_questions=(
                "What is happening now?",
                "Why does the candidate qualify?",
                "What happened in historically comparable cases?",
                "What is the validated risk profile?",
            ),
            required_contracts=(
                "CandidateDetailView",
                "PriceChartView",
                "EvidenceProfileView",
                "RiskSummaryView",
                "ProvenanceSummary",
            ),
            controls=(
                _display_control("chart-range", "Chart range", "ui.candidate.chart_range"),
                _display_control("chart-overlays", "Chart overlays", "ui.candidate.overlays"),
            ),
            charts=(
                ChartSpec(
                    chart_id="candidate-price-context",
                    title="Current structure",
                    kind=ChartKind.CANDLESTICK,
                    source_contract="PriceChartView",
                    required_fields=(
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "structural_levels",
                        "event_markers",
                    ),
                    x_semantics="trading session",
                    y_semantics="declared canonical price representation",
                    empty_state_message="Canonical chart context is unavailable for this candidate.",
                    canonical_price_basis_required=True,
                ),
                ChartSpec(
                    chart_id="candidate-mae-mfe",
                    title="Comparable-event MAE versus MFE",
                    kind=ChartKind.SCATTER,
                    source_contract="EvidenceProfileView",
                    required_fields=("mae", "mfe", "sample_count"),
                    x_semantics="maximum adverse excursion",
                    y_semantics="maximum favorable excursion",
                    empty_state_message="Comparable-event excursion evidence is unavailable.",
                ),
                ChartSpec(
                    chart_id="candidate-outcomes",
                    title="Comparable forward outcomes",
                    kind=ChartKind.DISTRIBUTION,
                    source_contract="EvidenceProfileView",
                    required_fields=("horizon", "return_distribution", "sample_count"),
                    x_semantics="forward return",
                    y_semantics="frequency or density",
                    empty_state_message="Comparable forward-outcome evidence is unavailable.",
                ),
            ),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.EXPERIMENTS,
            title="Experiment Library",
            route="/experiments",
            purpose="Search, compare, reproduce, and trace the complete research record.",
            primary_questions=(
                "Which experiment produced this claim?",
                "How did a follow-up configuration differ from its parent?",
                "Can the result be reproduced from its manifest?",
            ),
            required_contracts=(
                "ExperimentSummary",
                "ExperimentComparisonView",
                "ExperimentManifestView",
                "ProvenanceSummary",
            ),
            controls=(
                _display_control(
                    "experiment-search", "Search experiments", "ui.experiments.search"
                ),
                _display_control("experiment-status", "Research status", "ui.experiments.status"),
            ),
            charts=(
                ChartSpec(
                    chart_id="experiment-fold-performance",
                    title="Validation-fold performance",
                    kind=ChartKind.BAR,
                    source_contract="ExperimentComparisonView",
                    required_fields=("fold_id", "effect_value", "sample_count"),
                    x_semantics="time-ordered validation fold",
                    y_semantics="already-computed effect statistic",
                    empty_state_message="No validation-fold results are attached.",
                ),
            ),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.DATA_HEALTH,
            title="Data Health",
            route="/data-health",
            purpose="Expose freshness, quality, provider, discrepancy, and quarantine state.",
            primary_questions=(
                "Is the selected dataset trustworthy enough for downstream work?",
                "Which data defects or review items remain unresolved?",
                "Is scanner freshness currently blocked?",
            ),
            required_contracts=("DataHealthSummary", "ProviderHealthSummary", "ProvenanceSummary"),
            controls=(
                _display_control(
                    "quality-status", "Quality status", "ui.data_health.quality_status"
                ),
                _display_control("provider-filter", "Provider", "ui.data_health.provider"),
            ),
            charts=(
                ChartSpec(
                    chart_id="data-health-timeline",
                    title="Operational data-health timeline",
                    kind=ChartKind.STATUS_TIMELINE,
                    source_contract="DataHealthTimelineView",
                    required_fields=("observed_at", "state", "event_type"),
                    x_semantics="observation time",
                    y_semantics="classified operational state",
                    empty_state_message="No data-health timeline has been recorded.",
                ),
            ),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.ALERTS,
            title="Alerts",
            route="/alerts",
            purpose="Configure communication preferences for approved scanner-state transitions.",
            primary_questions=(
                "Which validated state transitions should be communicated?",
                "Which deliveries were suppressed or failed?",
            ),
            required_contracts=("AlertRuleView", "AlertHistoryView", "ProvenanceSummary"),
            controls=(
                _display_control("alert-category", "Alert category", "ui.alerts.category"),
                _display_control("alert-history", "History filter", "ui.alerts.history_filter"),
            ),
            charts=(),
            provenance_panel_required=True,
        ),
        WorkspaceBlueprint(
            workspace_id=WorkspaceId.SYSTEM,
            title="System / Project",
            route="/system",
            purpose="Expose build, version, documentation, and operational project status.",
            primary_questions=(
                "Which software and specification versions are active?",
                "Which project gates are open or blocked?",
            ),
            required_contracts=("SystemProjectView", "ProvenanceSummary"),
            controls=(),
            charts=(),
            provenance_panel_required=True,
        ),
    )
    navigation = tuple(
        NavigationItem(
            workspace_id=item.workspace_id,
            label=item.title,
            route=item.route,
            description=item.purpose,
        )
        for item in workspaces
    )
    return DashboardBlueprint(
        version="dashboard-visualization-architecture-v0.2",
        navigation=navigation,
        workspaces=workspaces,
    )


def _analytical_control(control_id: str, label: str, source_path: str) -> ControlBinding:
    return ControlBinding(
        control_id=control_id,
        label=label,
        kind=ControlBindingKind.ANALYTICAL_CONFIG,
        source_path=source_path,
        requires_resolved_configuration_review=True,
    )


def _display_control(control_id: str, label: str, source_path: str) -> ControlBinding:
    return ControlBinding(
        control_id=control_id,
        label=label,
        kind=ControlBindingKind.DISPLAY_STATE,
        source_path=source_path,
        requires_resolved_configuration_review=False,
    )


__all__ = [
    "ChartKind",
    "ChartSpec",
    "ControlBinding",
    "ControlBindingKind",
    "DashboardBlueprint",
    "NavigationItem",
    "WorkspaceBlueprint",
    "WorkspaceId",
    "default_dashboard_blueprint",
]
