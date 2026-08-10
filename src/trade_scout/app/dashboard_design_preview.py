"""Synthetic, framework-neutral preview for the dashboard architecture.

This module exists to inspect the user workflow before a front-end framework is selected. It uses
only immutable presentation contracts and synthetic data. Display filtering changes which rows are
shown; it never mutates a strategy, experiment configuration, evidence profile, or candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape

from trade_scout.api.dashboard_architecture import (
    ControlBindingKind,
    DashboardBlueprint,
    WorkspaceBlueprint,
    WorkspaceId,
    default_dashboard_blueprint,
)
from trade_scout.api.dashboard_contracts import (
    EvidenceSummary,
    HealthState,
    ProvenanceSummary,
    ScannerCandidateSummary,
)


@dataclass(frozen=True, slots=True)
class ScannerDisplayFilter:
    """Presentation-only scanner state that cannot change analytical eligibility."""

    candidate_states: tuple[str, ...] = ()
    search_text: str = ""


def filter_scanner_candidates(
    candidates: tuple[ScannerCandidateSummary, ...],
    display_filter: ScannerDisplayFilter,
) -> tuple[ScannerCandidateSummary, ...]:
    """Return a presentation subset while preserving the original candidate contracts."""

    state_filter = {value.strip().upper() for value in display_filter.candidate_states if value.strip()}
    search = display_filter.search_text.strip().casefold()
    return tuple(
        candidate
        for candidate in candidates
        if (not state_filter or candidate.candidate_state.upper() in state_filter)
        and (
            not search
            or search in candidate.symbol.casefold()
            or search in candidate.company_name.casefold()
        )
    )


def synthetic_scanner_candidates() -> tuple[ScannerCandidateSummary, ...]:
    """Return deterministic fake candidates for wireframe inspection only."""

    provenance = ProvenanceSummary(
        dataset_version="synthetic-dataset-v0",
        strategy_version="synthetic-strategy-v0",
        feature_set_version="synthetic-features-v0",
        risk_policy_version=None,
        ranking_model_version=None,
        run_id="synthetic-scan-run",
        as_of_date=date(2026, 8, 7),
        software_version="design-preview",
    )
    return (
        ScannerCandidateSummary(
            instrument_id="tsi_synthetic_alpha",
            symbol="ALFA",
            company_name="Synthetic Alpha Corp",
            candidate_state="TRIGGER_READY",
            strategy_version="synthetic-strategy-v0",
            pattern_duration_sessions=30,
            distance_to_trigger_fraction=0.012,
            evidence=EvidenceSummary(
                sample_size=240,
                positive_outcome_fraction=0.61,
                uncertainty_low=0.55,
                uncertainty_high=0.67,
                expectancy=0.043,
                mae_median=-0.031,
                mfe_median=0.087,
            ),
            risk_summary="Synthetic preview only; no production risk policy attached.",
            data_freshness=HealthState.PASS,
            transparent_rank_value=None,
            provenance=provenance,
        ),
        ScannerCandidateSummary(
            instrument_id="tsi_synthetic_beta",
            symbol="BETA",
            company_name="Synthetic Beta Industries",
            candidate_state="QUALIFIED",
            strategy_version="synthetic-strategy-v0",
            pattern_duration_sessions=45,
            distance_to_trigger_fraction=0.038,
            evidence=EvidenceSummary(
                sample_size=510,
                positive_outcome_fraction=0.57,
                uncertainty_low=0.53,
                uncertainty_high=0.61,
                expectancy=0.028,
                mae_median=-0.026,
                mfe_median=0.071,
            ),
            risk_summary="Synthetic preview only; no production risk policy attached.",
            data_freshness=HealthState.PASS,
            transparent_rank_value=None,
            provenance=provenance,
        ),
        ScannerCandidateSummary(
            instrument_id="tsi_synthetic_gamma",
            symbol="GAMM",
            company_name="Synthetic Gamma Holdings",
            candidate_state="FORMING",
            strategy_version="synthetic-strategy-v0",
            pattern_duration_sessions=18,
            distance_to_trigger_fraction=None,
            evidence=EvidenceSummary(
                sample_size=0,
                positive_outcome_fraction=None,
                uncertainty_low=None,
                uncertainty_high=None,
                expectancy=None,
                mae_median=None,
                mfe_median=None,
            ),
            risk_summary="No validated evidence attached to the synthetic forming state.",
            data_freshness=HealthState.PASS,
            transparent_rank_value=None,
            provenance=provenance,
        ),
    )


def render_dashboard_design_preview(
    blueprint: DashboardBlueprint | None = None,
    *,
    scanner_filter: ScannerDisplayFilter | None = None,
) -> str:
    """Render a self-contained architecture/wireframe preview with synthetic data."""

    architecture = blueprint or default_dashboard_blueprint()
    active_filter = scanner_filter or ScannerDisplayFilter()
    all_candidates = synthetic_scanner_candidates()
    visible_candidates = filter_scanner_candidates(all_candidates, active_filter)
    nav = "".join(
        f'<a href="#{escape(item.workspace_id.value)}">{escape(item.label)}</a>'
        for item in architecture.navigation
    )
    sections = "".join(
        _render_workspace(
            workspace,
            candidates=visible_candidates if workspace.workspace_id is WorkspaceId.SCANNER else (),
            total_candidate_count=(
                len(all_candidates) if workspace.workspace_id is WorkspaceId.SCANNER else None
            ),
        )
        for workspace in architecture.workspaces
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Dashboard Architecture Preview</title>
<style>
:root {{ --bg:#0b0f15; --panel:#121923; --panel2:#171f2b; --line:#2a3545; --text:#eef2f7; --muted:#9caabd; --accent:#f0c84d; --analytical:#f2bd60; --display:#75c7ff; --good:#6fd3a0; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
header {{ padding:30px clamp(20px,4vw,56px) 18px; border-bottom:1px solid var(--line); }}
h1 {{ margin:0 0 6px; font-size:28px; }}
h2 {{ margin:0; font-size:20px; }}
h3 {{ margin:0 0 8px; font-size:14px; }}
.subtle {{ color:var(--muted); }}
.banner {{ margin-top:14px; border:1px solid #5a4b25; background:#1f1a0d; border-radius:9px; padding:11px 13px; }}
nav {{ position:sticky; top:0; z-index:2; display:flex; flex-wrap:wrap; gap:7px; padding:10px clamp(20px,4vw,56px); background:#0d1219ef; border-bottom:1px solid var(--line); backdrop-filter:blur(8px); }}
nav a {{ color:var(--muted); text-decoration:none; border:1px solid var(--line); border-radius:999px; padding:5px 9px; }}
main {{ max-width:1500px; margin:0 auto; padding:6px clamp(20px,4vw,56px) 70px; }}
.workspace {{ padding-top:34px; scroll-margin-top:54px; }}
.head {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:12px; }}
.route {{ font-family:ui-monospace,monospace; color:var(--accent); }}
.grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:12px; }}
.card {{ grid-column:span 6; min-width:0; border:1px solid var(--line); background:var(--panel); border-radius:11px; padding:14px; }}
.wide {{ grid-column:1/-1; }}
.questions li, .contracts li {{ margin:5px 0; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }}
tr:last-child td {{ border-bottom:0; }}
.tag {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 7px; font-size:10px; font-weight:750; letter-spacing:.04em; }}
.analytical {{ color:var(--analytical); }} .display {{ color:var(--display); }}
.chart-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
.chart {{ min-height:150px; background:var(--panel2); border:1px dashed #435168; border-radius:9px; padding:12px; }}
.chart-meta {{ margin-top:8px; color:var(--muted); font-size:11px; }}
.provenance {{ border-left:3px solid var(--accent); padding-left:10px; }}
.candidate-state {{ color:var(--good); font-weight:750; }}
footer {{ margin-top:36px; color:var(--muted); border-top:1px solid var(--line); padding-top:18px; }}
@media(max-width:850px) {{ .card {{ grid-column:1/-1; }} .chart-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>Trade Scout dashboard architecture</h1>
  <div class="subtle">{escape(architecture.version)} · framework-neutral · synthetic design preview</div>
  <div class="banner"><strong>No analytical logic lives here.</strong> Analytical controls bind to validated configuration; display filters change presentation only. All market/evidence values below are synthetic.</div>
</header>
<nav>{nav}</nav>
<main>
{sections}
<footer>Design preview only. No provider calls, canonical promotion, experiment execution, ranking calculation, alert delivery, or trade execution occurs in this renderer.</footer>
</main>
</body>
</html>
"""


def _render_workspace(
    workspace: WorkspaceBlueprint,
    *,
    candidates: tuple[ScannerCandidateSummary, ...],
    total_candidate_count: int | None,
) -> str:
    questions = "".join(f"<li>{escape(item)}</li>" for item in workspace.primary_questions)
    contracts = "".join(f"<li><code>{escape(item)}</code></li>" for item in workspace.required_contracts)
    controls = _render_controls(workspace)
    charts = _render_charts(workspace)
    scanner = (
        _render_scanner_demo(candidates, total_candidate_count or 0)
        if workspace.workspace_id is WorkspaceId.SCANNER
        else ""
    )
    return f"""
<section id="{escape(workspace.workspace_id.value)}" class="workspace">
  <div class="head">
    <div><h2>{escape(workspace.title)}</h2><div class="subtle">{escape(workspace.purpose)}</div></div>
    <span class="route">{escape(workspace.route)}</span>
  </div>
  <div class="grid">
    <div class="card"><h3>Questions this screen must answer</h3><ul class="questions">{questions}</ul></div>
    <div class="card"><h3>Application/API contracts consumed</h3><ul class="contracts">{contracts}</ul></div>
    <div class="card wide"><h3>Control boundary</h3>{controls}</div>
    {charts}
    {scanner}
    <div class="card wide provenance"><strong>Provenance panel:</strong> {"required" if workspace.provenance_panel_required else "optional"}. Analytical logic allowed in workspace: <strong>NO</strong>.</div>
  </div>
</section>
"""


def _render_controls(workspace: WorkspaceBlueprint) -> str:
    if not workspace.controls:
        return '<div class="subtle">No user-editable controls are required in this blueprint.</div>'
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.label)}</td>"
        f"<td><span class='tag {'analytical' if item.kind is ControlBindingKind.ANALYTICAL_CONFIG else 'display'}'>{escape(item.kind.value)}</span></td>"
        f"<td><code>{escape(item.source_path)}</code></td>"
        f"<td>{'YES' if item.requires_resolved_configuration_review else 'NO'}</td>"
        "</tr>"
        for item in workspace.controls
    )
    return f"<table><thead><tr><th>Control</th><th>State kind</th><th>Source of truth</th><th>Resolved config review</th></tr></thead><tbody>{rows}</tbody></table>"


def _render_charts(workspace: WorkspaceBlueprint) -> str:
    if not workspace.charts:
        return ""
    blocks = "".join(
        f"<div class='chart'><strong>{escape(item.title)}</strong><div class='subtle'>{escape(item.kind.value)} · {escape(item.chart_id)}</div><div class='chart-meta'>Source: <code>{escape(item.source_contract)}</code><br>Fields: {escape(', '.join(item.required_fields))}<br>X: {escape(item.x_semantics)}<br>Y: {escape(item.y_semantics)}<br>Canonical price basis required: {'YES' if item.canonical_price_basis_required else 'NO'}<br>Empty state: {escape(item.empty_state_message)}</div></div>"
        for item in workspace.charts
    )
    return f"<div class='card wide'><h3>Chart / visualization contract</h3><div class='chart-grid'>{blocks}</div></div>"


def _render_scanner_demo(
    candidates: tuple[ScannerCandidateSummary, ...],
    total_candidate_count: int,
) -> str:
    rows = "".join(
        "<tr>"
        f"<td><strong>{escape(item.symbol)}</strong><br><span class='subtle'>{escape(item.company_name)}</span></td>"
        f"<td class='candidate-state'>{escape(item.candidate_state)}</td>"
        f"<td>{item.pattern_duration_sessions if item.pattern_duration_sessions is not None else '—'}</td>"
        f"<td>{item.evidence.sample_size}</td>"
        f"<td>{_probability(item.evidence.positive_outcome_fraction)}</td>"
        f"<td>{escape(item.data_freshness.value)}</td>"
        "</tr>"
        for item in candidates
    ) or "<tr><td colspan='6' class='subtle'>No rows match the current display filter.</td></tr>"
    return f"""
<div class="card wide">
  <h3>Scanner display-filter demonstration</h3>
  <div class="subtle">Showing {len(candidates)} of {total_candidate_count} synthetic candidates. The source candidate tuple and evidence contracts are unchanged.</div>
  <table><thead><tr><th>Candidate</th><th>State</th><th>Base sessions</th><th>Historical N</th><th>Positive fraction</th><th>Freshness</th></tr></thead><tbody>{rows}</tbody></table>
</div>
"""


def _probability(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


__all__ = [
    "ScannerDisplayFilter",
    "filter_scanner_candidates",
    "render_dashboard_design_preview",
    "synthetic_scanner_candidates",
]
