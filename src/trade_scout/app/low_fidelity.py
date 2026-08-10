"""Low-fidelity, dependency-free Trade Scout dashboard prototype.

The renderer accepts presentation-ready API contracts and only formats them. It deliberately
contains no feature, pattern, event, risk, statistics, ranking, provider, or experiment logic.
"""

from __future__ import annotations

from html import escape

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    HealthState,
    ProvenanceSummary,
    ScannerCandidateSummary,
)


def render_application_html(snapshot: ApplicationSnapshot) -> str:
    """Render a self-contained HTML wireframe from one application snapshot."""

    notices = "".join(f"<li>{escape(item)}</li>" for item in snapshot.global_notices)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trade Scout — Application Prototype</title>
<style>
:root {{
  color-scheme: dark;
  --bg: #0b0e13;
  --panel: #121720;
  --panel-2: #171d27;
  --border: #293241;
  --text: #edf1f7;
  --muted: #98a6b8;
  --accent: #f1c84b;
  --good: #63d39a;
  --warn: #f2bd60;
  --bad: #ef7b7b;
  --blocked: #c894ed;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
a {{ color: inherit; text-decoration: none; }}
.shell {{ min-height: 100vh; display: grid; grid-template-columns: 230px minmax(0, 1fr); }}
.sidebar {{ position: sticky; top: 0; height: 100vh; border-right: 1px solid var(--border); padding: 22px 16px; background: #0d1118; }}
.brand {{ font-size: 19px; font-weight: 760; letter-spacing: .01em; }}
.phase {{ margin-top: 4px; color: var(--accent); font-size: 12px; }}
.nav {{ display: grid; gap: 6px; margin-top: 28px; }}
.nav a {{ color: var(--muted); padding: 9px 10px; border-radius: 7px; }}
.nav a:hover, .nav a:focus {{ background: var(--panel-2); color: var(--text); outline: none; }}
.nav .current {{ color: var(--text); background: var(--panel-2); border: 1px solid var(--border); }}
.side-note {{ position: absolute; bottom: 22px; left: 16px; right: 16px; color: var(--muted); font-size: 11px; }}
main {{ padding: 28px clamp(20px, 4vw, 52px) 80px; max-width: 1500px; width: 100%; }}
.header {{ display: flex; gap: 24px; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }}
h1 {{ font-size: 26px; margin: 0 0 5px; }}
h2 {{ font-size: 18px; margin: 0; }}
h3 {{ font-size: 14px; margin: 0; }}
.subtle {{ color: var(--muted); }}
.pill {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border); border-radius: 999px; padding: 5px 9px; font-size: 11px; font-weight: 700; letter-spacing: .035em; }}
.PASS {{ color: var(--good); }} .WARN {{ color: var(--warn); }} .QUARANTINE {{ color: var(--bad); }} .BLOCKED {{ color: var(--blocked); }}
.notice {{ border: 1px solid #594b25; background: #1e1a0e; border-radius: 10px; padding: 12px 16px; margin: 0 0 22px; }}
.notice ul {{ margin: 0; padding-left: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; }}
.card {{ border: 1px solid var(--border); border-radius: 11px; background: var(--panel); padding: 16px; min-width: 0; }}
.span-3 {{ grid-column: span 3; }} .span-4 {{ grid-column: span 4; }} .span-5 {{ grid-column: span 5; }} .span-6 {{ grid-column: span 6; }} .span-7 {{ grid-column: span 7; }} .span-8 {{ grid-column: span 8; }} .span-12 {{ grid-column: 1 / -1; }}
.metric-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }}
.metric {{ font-size: 25px; font-weight: 740; margin-top: 5px; }}
.section {{ scroll-margin-top: 20px; margin-top: 35px; }}
.section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 9px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
th {{ color: var(--muted); font-size: 11px; font-weight: 650; text-transform: uppercase; letter-spacing: .05em; }}
tr:last-child td {{ border-bottom: 0; }}
.kv {{ display: grid; grid-template-columns: minmax(130px, .8fr) minmax(0, 1.4fr); gap: 7px 14px; }}
.kv dt {{ color: var(--muted); }} .kv dd {{ margin: 0; overflow-wrap: anywhere; }}
.blocker {{ border-left: 3px solid var(--blocked); padding-left: 10px; margin-top: 9px; }}
.mode {{ font-weight: 750; letter-spacing: .04em; }}
.EXPLORATORY {{ color: var(--warn); }} .VALIDATING {{ color: #7fc8ff; }} .VALIDATED, .PRODUCTION_ELIGIBLE {{ color: var(--good); }}
.preview-table {{ opacity: .92; }}
.empty-state {{ border: 1px dashed #3d4859; border-radius: 9px; padding: 18px; color: var(--muted); }}
.provenance {{ margin-top: 14px; border-top: 1px solid var(--border); padding-top: 12px; }}
.provenance summary {{ cursor: pointer; color: var(--muted); }}
footer {{ color: var(--muted); margin-top: 38px; font-size: 11px; }}
@media (max-width: 900px) {{
  .shell {{ grid-template-columns: 1fr; }}
  .sidebar {{ position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--border); }}
  .nav {{ grid-template-columns: repeat(3, 1fr); }}
  .side-note {{ position: static; margin-top: 18px; }}
  .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 {{ grid-column: 1 / -1; }}
}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">Trade Scout</div>
    <div class="phase">{escape(snapshot.active_phase)}</div>
    <nav class="nav" aria-label="Primary">
      <a href="#research">Research</a>
      <a href="#scanner">Scanner</a>
      <a href="#experiments">Experiments</a>
      <a class="current" href="#data-health">Data Health</a>
      <a href="#alerts">Alerts</a>
      <a href="#system">System</a>
    </nav>
    <div class="side-note">Research first · Validate second · Scan third · Alert last</div>
  </aside>
  <main>
    <header class="header">
      <div>
        <h1>Research console</h1>
        <div class="subtle">Evidence, provenance, and failure state before presentation polish.</div>
      </div>
      <span class="pill">BUILD {escape(snapshot.build_label)}</span>
    </header>
    {f'<div class="notice"><ul>{notices}</ul></div>' if notices else ""}

    <section id="data-health" class="section">
      <div class="section-head">
        <div><h2>Data Health</h2><div class="subtle">Phase-gating view for provider, quality, and freshness state.</div></div>
        {_state_pill(snapshot.data_health.state)}
      </div>
      {_render_data_health(snapshot)}
    </section>

    <section id="research" class="section">
      <div class="section-head">
        <div><h2>Research Lab</h2><div class="subtle">Configuration shell only; analytical controls must come from validated schemas.</div></div>
        <span class="pill">{escape(snapshot.research.workspace_state)}</span>
      </div>
      {_render_research(snapshot)}
    </section>

    <section id="scanner" class="section">
      <div class="section-head">
        <div><h2>Market Scanner</h2><div class="subtle">Normal candidate output is blocked when freshness or production eligibility fails.</div></div>
        {_state_pill(snapshot.scanner.freshness_gate)}
      </div>
      {_render_scanner(snapshot)}
    </section>

    <section id="experiments" class="section">
      <div class="section-head">
        <div><h2>Experiment Library</h2><div class="subtle">Immutable lineage, including null and rejected work.</div></div>
      </div>
      {_render_experiments(snapshot)}
    </section>

    <section id="alerts" class="section">
      <div class="section-head"><div><h2>Alerts</h2><div class="subtle">Deferred until validated scanner lifecycle states exist.</div></div><span class="pill BLOCKED">BLOCKED</span></div>
      <div class="empty-state">No notification controls are enabled in the Phase 1 prototype. There are no brokerage actions or one-click trade controls.</div>
    </section>

    <section id="system" class="section">
      <div class="section-head"><div><h2>System / Project</h2><div class="subtle">Build and application snapshot identity.</div></div></div>
      <div class="card"><dl class="kv"><dt>Build</dt><dd>{escape(snapshot.build_label)}</dd><dt>Active phase</dt><dd>{escape(snapshot.active_phase)}</dd><dt>Snapshot generated</dt><dd>{escape(snapshot.generated_at.isoformat())}</dd></dl></div>
    </section>

    <footer>Synthetic UI shell. The renderer performs presentation only and must never become an analytical implementation.</footer>
  </main>
</div>
</body>
</html>
"""


def _render_data_health(snapshot: ApplicationSnapshot) -> str:
    health = snapshot.data_health
    provider_rows = "".join(
        "<tr>"
        f"<td><strong>{escape(item.display_name)}</strong><br><span class='subtle'>{escape(item.provider_id)}</span></td>"
        f"<td>{escape(item.role)}</td>"
        f"<td>{_state_pill(item.state)}</td>"
        f"<td>{escape(item.latest_successful_session.isoformat()) if item.latest_successful_session else '—'}</td>"
        f"<td>{escape(item.message)}</td>"
        "</tr>"
        for item in health.providers
    )
    return f"""
<div class="grid">
  {_metric("Dataset version", health.dataset_version or "Not promoted", "span-3")}
  {_metric("Latest canonical session", health.latest_canonical_session.isoformat() if health.latest_canonical_session else "None", "span-3")}
  {_metric("Quarantined", str(health.quality_counts.quarantined), "span-3")}
  {_metric("Scanner freshness", health.scanner_freshness_gate, "span-3", state=health.scanner_freshness_gate)}
  <div class="card span-4"><div class="metric-label">Quality states</div><dl class="kv"><dt>PASS</dt><dd>{health.quality_counts.passed}</dd><dt>WARN</dt><dd>{health.quality_counts.warned}</dd><dt>QUARANTINE</dt><dd>{health.quality_counts.quarantined}</dd></dl></div>
  <div class="card span-4"><div class="metric-label">Review pressure</div><dl class="kv"><dt>Missing-data anomalies</dt><dd>{health.missing_data_anomaly_count}</dd><dt>Cross-provider discrepancies</dt><dd>{health.cross_provider_discrepancy_count}</dd><dt>Corporate-action anomalies</dt><dd>{health.corporate_action_anomaly_count}</dd></dl></div>
  <div class="card span-4"><div class="metric-label">Operations</div><dl class="kv"><dt>Failed ingestion jobs</dt><dd>{health.failed_ingestion_job_count}</dd><dt>Current assessment</dt><dd>{escape(health.message)}</dd></dl></div>
  <div class="card span-12"><h3>Provider status</h3><table><thead><tr><th>Provider</th><th>Role</th><th>State</th><th>Latest session</th><th>Evidence / constraint</th></tr></thead><tbody>{provider_rows}</tbody></table>{_provenance(health.provenance)}</div>
</div>
"""


def _render_research(snapshot: ApplicationSnapshot) -> str:
    research = snapshot.research
    blockers = "".join(
        f"<div class='blocker'>{escape(item)}</div>" for item in research.blocking_reasons
    )
    return f"""
<div class="grid">
  <div class="card span-7">
    <div class="metric-label">Experiment draft</div>
    <dl class="kv">
      <dt>Strategy family</dt><dd>{escape(research.strategy_family)}</dd>
      <dt>Universe</dt><dd>{escape(research.universe_label)}</dd>
      <dt>Dataset</dt><dd>{escape(research.dataset_label)}</dd>
      <dt>Mode</dt><dd><span class="mode {escape(research.research_mode)}">{escape(research.research_mode)}</span></dd>
      <dt>Resolved configuration</dt><dd>{escape(research.resolved_configuration_id or "Not resolved")}</dd>
      <dt>Launch</dt><dd>{"ENABLED" if research.launch_enabled else "BLOCKED"}</dd>
    </dl>
    {blockers}
    {_provenance(research.provenance)}
  </div>
  <div class="card span-5">
    <div class="metric-label">Required launch sequence</div>
    <ol>
      <li>Select approved dataset and point-in-time universe.</li>
      <li>Load controls from validated configuration schema.</li>
      <li>Show the complete resolved configuration.</li>
      <li>Create an immutable experiment record.</li>
      <li>Launch only through application services.</li>
    </ol>
    <div class="subtle">The prototype intentionally does not invent configuration fields while the data foundation remains incomplete.</div>
  </div>
</div>
"""


def _render_scanner(snapshot: ApplicationSnapshot) -> str:
    scanner = snapshot.scanner
    blockers = "".join(
        f"<div class='blocker'>{escape(item)}</div>" for item in scanner.blocking_reasons
    )
    if not scanner.candidates:
        rows = "<tr><td colspan='8' class='subtle'>No normal candidate rows available.</td></tr>"
    else:
        rows = "".join(_candidate_row(item) for item in scanner.candidates)
    return f"""
<div class="card">
  <div class="grid">
    {_metric("As-of", scanner.as_of_date.isoformat() if scanner.as_of_date else "—", "span-3")}
    {_metric("Candidates", str(len(scanner.candidates)), "span-3")}
    {_metric("Freshness gate", scanner.freshness_gate, "span-3", state=scanner.freshness_gate)}
    {_metric("Workspace", scanner.workspace_state, "span-3")}
  </div>
  {blockers}
  <div style="overflow-x:auto; margin-top:14px"><table class="preview-table"><thead><tr><th>Symbol</th><th>State</th><th>Strategy</th><th>N</th><th>Positive outcome</th><th>Expectancy</th><th>Risk</th><th>Freshness</th></tr></thead><tbody>{rows}</tbody></table></div>
  {_provenance(scanner.provenance)}
</div>
"""


def _candidate_row(candidate: ScannerCandidateSummary) -> str:
    probability = _percentage(candidate.evidence.positive_outcome_fraction)
    expectancy = _number(candidate.evidence.expectancy)
    return (
        "<tr>"
        f"<td><strong>{escape(candidate.symbol)}</strong><br><span class='subtle'>{escape(candidate.company_name)}</span></td>"
        f"<td>{escape(candidate.candidate_state)}</td>"
        f"<td>{escape(candidate.strategy_version)}</td>"
        f"<td>{candidate.evidence.sample_size}</td>"
        f"<td>{probability}</td>"
        f"<td>{expectancy}</td>"
        f"<td>{escape(candidate.risk_summary)}</td>"
        f"<td>{_state_pill(candidate.data_freshness)}</td>"
        "</tr>"
    )


def _render_experiments(snapshot: ApplicationSnapshot) -> str:
    if not snapshot.experiments:
        return '<div class="empty-state">No experiment records are available in this prototype snapshot.</div>'
    rows = "".join(
        "<tr>"
        f"<td><strong>{escape(item.experiment_id)}</strong><br><span class='subtle'>{escape(item.display_name)}</span></td>"
        f"<td>{escape(item.strategy_family)}</td>"
        f"<td><span class='mode {escape(item.research_state)}'>{escape(item.research_state)}</span></td>"
        f"<td>{escape(item.dataset_version)}</td>"
        f"<td>{escape(item.code_version)}</td>"
        f"<td>{escape(item.parent_experiment_id or '—')}</td>"
        f"<td>{escape(item.decision)}</td>"
        "</tr>"
        for item in snapshot.experiments
    )
    return f'<div class="card"><table><thead><tr><th>Experiment</th><th>Family</th><th>Status</th><th>Dataset</th><th>Code</th><th>Parent</th><th>Decision</th></tr></thead><tbody>{rows}</tbody></table></div>'


def _metric(label: str, value: str, width: str, *, state: HealthState | None = None) -> str:
    state_class = f" {escape(state)}" if state is not None else ""
    return f'<div class="card {width}"><div class="metric-label">{escape(label)}</div><div class="metric{state_class}">{escape(str(value))}</div></div>'


def _state_pill(state: HealthState) -> str:
    return f'<span class="pill {escape(state)}">{escape(state)}</span>'


def _percentage(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def _provenance(provenance: ProvenanceSummary) -> str:
    values = (
        ("Dataset", provenance.dataset_version),
        ("Strategy", provenance.strategy_version),
        ("Feature set", provenance.feature_set_version),
        ("Risk policy", provenance.risk_policy_version),
        ("Ranking model", provenance.ranking_model_version),
        ("Run ID", provenance.run_id),
        ("As-of", provenance.as_of_date.isoformat() if provenance.as_of_date else None),
        ("Software", provenance.software_version),
    )
    rows = "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(value or '—')}</dd>" for label, value in values
    )
    return f'<details class="provenance"><summary>Provenance</summary><dl class="kv">{rows}</dl></details>'
