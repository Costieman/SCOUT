# ruff: noqa: E501
"""Operational presentation layer for the Phase 1 Data Health console.

This module only formats already-classified application state. It adds campaign progress,
recent provider-control telemetry, review pressure, and explicit Phase 1 blockers to the existing
low-fidelity shell. It contains no provider calls or analytical calculations.
"""

from __future__ import annotations

from html import escape

from trade_scout.api.dashboard_contracts import (
    ApplicationSnapshot,
    DataHealthSummary,
    ProviderHealthSummary,
)
from trade_scout.app.low_fidelity import render_application_html

_PROVIDER_MARKER = '<div class="card span-12"><h3>Provider status</h3>'
_STYLE_MARKER = "</style>"


def render_operational_application_html(snapshot: ApplicationSnapshot) -> str:
    """Add operational Phase 1 controls to the stable low-fidelity application shell."""

    html = render_application_html(snapshot)
    if _PROVIDER_MARKER not in html or _STYLE_MARKER not in html:
        raise RuntimeError("low-fidelity renderer no longer exposes expected insertion markers")
    html = html.replace(_STYLE_MARKER, _operational_css() + _STYLE_MARKER, 1)
    return html.replace(
        _PROVIDER_MARKER,
        _render_operational_panel(snapshot.data_health) + _PROVIDER_MARKER,
        1,
    )


def _render_operational_panel(health: DataHealthSummary) -> str:
    blocker_items = "".join(f"<li>{escape(item)}</li>" for item in health.phase_blockers)
    if blocker_items:
        blockers = f'<ol class="phase-blocker-list">{blocker_items}</ol>'
        blocker_state = f"{len(health.phase_blockers)} open"
    else:
        blockers = '<div class="empty-state">No Phase 1 blockers are recorded.</div>'
        blocker_state = "None"

    provider_cards = "".join(
        _provider_operations(item) for item in health.providers if _has_operational_detail(item)
    )
    if not provider_cards:
        provider_cards = (
            '<div class="empty-state">No provider operational telemetry supplied.</div>'
        )

    return f"""
  <div class="card span-12 operational-panel">
    <div class="operational-heading">
      <div>
        <div class="metric-label">Phase 1 control plane</div>
        <h3>What is blocking the data foundation?</h3>
      </div>
      <span class="pill">{escape(blocker_state)}</span>
    </div>
    <div class="operational-grid">
      <div class="operational-blockers">
        {blockers}
      </div>
      <div class="operational-summary">
        <dl class="kv">
          <dt>Cross-provider review work</dt><dd>{_count(health.review_work_item_count)}</dd>
          <dt>Missing-session observations</dt><dd>{_count(health.missing_data_anomaly_count)}</dd>
          <dt>Provider discrepancies</dt><dd>{_count(health.cross_provider_discrepancy_count)}</dd>
          <dt>Corporate-action anomalies</dt><dd>{_count(health.corporate_action_anomaly_count)}</dd>
          <dt>Failed ingestion markers</dt><dd>{_count(health.failed_ingestion_job_count)}</dd>
        </dl>
      </div>
    </div>
    <div class="provider-operations-grid">{provider_cards}</div>
  </div>
"""


def _provider_operations(provider: ProviderHealthSummary) -> str:
    progress = _progress(provider)
    observed = provider.last_observed_at.isoformat() if provider.last_observed_at else "Unknown"
    status = provider.operational_status or "Unknown"
    last_quota = provider.last_rate_limited_symbol or "—"
    last_failure = _last_failure(provider)
    return f"""
      <div class="provider-operation-card">
        <div class="provider-operation-head">
          <strong>{escape(provider.display_name)}</strong>
          <span class="pill {escape(provider.state.value)}">{escape(provider.state.value)}</span>
        </div>
        <div class="subtle">{escape(provider.role)}</div>
        {progress}
        <dl class="kv compact-kv">
          <dt>Operational status</dt><dd>{escape(status)}</dd>
          <dt>Last observed</dt><dd>{escape(observed)}</dd>
          <dt>Quota pauses</dt><dd>{_count(provider.quota_pause_count)}</dd>
          <dt>Failures</dt><dd>{_count(provider.failure_count)}</dd>
          <dt>Last rate-limited symbol</dt><dd>{escape(last_quota)}</dd>
          <dt>Last failure</dt><dd>{escape(last_failure)}</dd>
        </dl>
      </div>
"""


def _progress(provider: ProviderHealthSummary) -> str:
    current = provider.progress_current
    total = provider.progress_total
    if current is None or total is None:
        return '<div class="progress-unknown subtle">Campaign progress not supplied.</div>'
    percentage = 100.0 if total == 0 else (current / total) * 100.0
    label = provider.progress_label or "items"
    return f"""
        <div class="progress-copy">
          <span>{current}/{total} {escape(label)}</span><span>{percentage:.1f}%</span>
        </div>
        <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="{total}" aria-valuenow="{current}">
          <div class="progress-fill" style="width:{percentage:.4f}%"></div>
        </div>
"""


def _last_failure(provider: ProviderHealthSummary) -> str:
    if provider.last_failed_symbol is None and provider.last_failure_type is None:
        return "—"
    if provider.last_failed_symbol and provider.last_failure_type:
        return f"{provider.last_failed_symbol}: {provider.last_failure_type}"
    return provider.last_failed_symbol or provider.last_failure_type or "—"


def _has_operational_detail(provider: ProviderHealthSummary) -> bool:
    return any(
        value is not None
        for value in (
            provider.progress_current,
            provider.operational_status,
            provider.last_observed_at,
            provider.quota_pause_count,
            provider.failure_count,
            provider.last_rate_limited_symbol,
            provider.last_failed_symbol,
            provider.last_failure_type,
        )
    )


def _count(value: int | None) -> str:
    return "Unknown" if value is None else str(value)


def _operational_css() -> str:
    return """
.operational-panel { margin-bottom: 14px; }
.operational-heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
.operational-heading h3 { margin-top:4px; }
.operational-grid { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr); gap:18px; margin-top:14px; }
.operational-blockers { min-width:0; }
.phase-blocker-list { margin:0; padding-left:22px; }
.phase-blocker-list li { margin:0 0 8px; }
.provider-operations-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; margin-top:16px; }
.provider-operation-card { border:1px solid var(--border); background:var(--panel-2); border-radius:9px; padding:13px; }
.provider-operation-head { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.progress-copy { display:flex; justify-content:space-between; gap:12px; margin-top:13px; font-size:12px; }
.progress-track { height:8px; background:#242d3b; border-radius:999px; overflow:hidden; margin:6px 0 12px; }
.progress-fill { height:100%; background:var(--accent); min-width:0; }
.progress-unknown { margin:13px 0 12px; }
.compact-kv { font-size:12px; grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr); }
@media (max-width:900px) { .operational-grid { grid-template-columns:1fr; } }
"""
