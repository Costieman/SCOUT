# ruff: noqa: E501
"""Presentation-only HTML for the user-facing Experiment Library."""

from __future__ import annotations

import json
from html import escape
from urllib.parse import urlencode

from trade_scout.app.experiment_library_service import (
    ExperimentLibraryDetail,
    ExperimentLibraryItem,
    ExperimentLibrarySnapshot,
    ExperimentResultSummary,
)
from trade_scout.experiments.contracts import (
    ExperimentStatus,
    JSONValue,
    ResearchMode,
)


def render_experiment_library_html(
    *,
    snapshot: ExperimentLibrarySnapshot,
    strategy_families: tuple[str, ...],
    detail: ExperimentLibraryDetail | None = None,
    comparison: tuple[ExperimentLibraryDetail, ...] = (),
    current_dataset_version: str | None = None,
    error: str | None = None,
) -> str:
    """Render searchable experiment history without making the dashboard authoritative."""

    selected = snapshot.filters
    warning = (
        f'<div class="error"><strong>Experiment Library error:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    sync_warnings = "".join(
        f"<li>{escape(item)}</li>" for item in snapshot.synchronization_warnings
    )
    sync_warning_block = (
        '<div class="error"><strong>Some manifests could not be indexed:</strong>'
        f"<ul>{sync_warnings}</ul></div>"
        if sync_warnings
        else ""
    )
    rows = "".join(_row(item) for item in snapshot.items)
    if not rows:
        rows = (
            '<tr><td colspan="9" class="subtle">'
            "No experiments match the current display filters.</td></tr>"
        )
    family_options = '<option value="">All strategy families</option>' + "".join(
        _option(item, item, selected.strategy_family) for item in strategy_families
    )
    detail_html = (
        _render_detail(detail, current_dataset_version=current_dataset_version)
        if detail is not None
        else ""
    )
    comparison_html = _render_comparison(comparison) if comparison else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Experiment Library</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1680px,96vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:18px; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:16px 0 8px; font-size:15px; }} .subtle {{ color:var(--muted); }}
.banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin:14px 0; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; min-width:0; margin-top:14px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s3 {{ grid-column:span 3; }} .s6 {{ grid-column:span 6; }}
form.filters {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} .u2 {{ grid-column:span 2; }} .u3 {{ grid-column:span 3; }} select,input,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:9px 10px; font:inherit; }} button,.button {{ cursor:pointer; display:inline-flex; align-items:center; justify-content:center; background:#2a2411; border:1px solid #6d5b24; color:#f7d66e; font-weight:760; border-radius:8px; padding:9px 11px; }}
.metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:22px; font-weight:760; margin-top:5px; }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:4px 8px; font-size:11px; font-weight:750; }} .bad {{ color:var(--bad); }} .blue {{ color:var(--blue); }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.03em; }} tr:last-child td {{ border-bottom:0; }} .scroll {{ overflow:auto; }} code {{ color:#d9e3ef; }} pre {{ margin:0; padding:12px; border:1px solid var(--border); border-radius:8px; background:#0c1118; overflow:auto; white-space:pre-wrap; word-break:break-word; }} details {{ margin-top:10px; }} ul {{ padding-left:19px; }} .compare-actions {{ display:flex; gap:10px; align-items:center; justify-content:flex-end; margin-top:10px; }} .status-failed {{ color:var(--bad); }} .status-succeeded {{ color:var(--good); }}
@media(max-width:1200px) {{ form.filters {{ grid-template-columns:1fr 1fr; }} form.filters > * {{ grid-column:auto !important; }} .s3,.s6 {{ grid-column:1/-1; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/">← Research console</a><h1>Experiment Library</h1><div class="subtle">Queryable view of immutable experiment manifests and their DuckDB registry index.</div></div><span class="pill">RESEARCH HISTORY</span></header>
<div class="banner"><strong>The registry is an index, not the evidence.</strong> This page reads checksum-verified manifests and artifacts as the source of truth. Failed, null and unfavorable experiments are not hidden. Display filters change only what you see.</div>
<div class="grid">
  <div class="card s3"><div class="metric-label">Verified manifests indexed</div><div class="metric blue">{snapshot.indexed_manifest_count}</div></div>
  <div class="card s3"><div class="metric-label">Rows shown</div><div class="metric">{len(snapshot.items)}</div></div>
  <div class="card s3"><div class="metric-label">Failed rows shown</div><div class="metric bad">{sum(item.record.status is ExperimentStatus.FAILED for item in snapshot.items)}</div></div>
  <div class="card s3"><div class="metric-label">Research mode</div><div class="metric">Mixed</div><div class="subtle">mode is shown per run; no promotion is inferred here</div></div>
</div>
<div class="card">
<h2>Search and display filters</h2>
<form class="filters" action="/research/experiments" method="get">
<label class="u3">ID / name / hypothesis<input name="q" value="{escape(selected.text)}" placeholder="exp_... or strategy name"></label>
<label class="u2">Execution status<select name="status">{_status_options(selected.status)}</select></label>
<label class="u2">Research mode<select name="mode">{_mode_options(selected.mode)}</select></label>
<label class="u2">Strategy family<select name="strategy_family">{family_options}</select></label>
<label class="u3">Dataset version<input name="dataset_version" value="{escape(selected.dataset_version or "")}" placeholder="exact version"></label>
<label class="u3">Code version<input name="code_version" value="{escape(selected.code_version or "")}" placeholder="exact commit"></label>
<label class="u3">Hypothesis family<input name="hypothesis_family_id" value="{escape(selected.hypothesis_family_id or "")}" placeholder="family ID"></label>
<button class="u2" type="submit">Apply filters</button>
<a class="button u2" href="/research/experiments">Clear</a>
</form>
</div>
{warning}{sync_warning_block}
<div class="card">
<h2>Experiment registry</h2>
<form action="/research/experiments" method="get">
<div class="scroll"><table><thead><tr><th>Compare</th><th>Created</th><th>Experiment</th><th>Strategy family</th><th>Mode</th><th>Status</th><th>Dataset</th><th>Result glimpse</th><th>Lineage</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="compare-actions"><span class="subtle">Select 2–4 rows for a configuration/result comparison. No composite score is calculated.</span><button type="submit">Compare selected</button></div>
</form>
</div>
{comparison_html}
{detail_html}
</div></body></html>"""


def _row(item: ExperimentLibraryItem) -> str:
    record = item.record
    status_class = (
        "status-succeeded" if record.status is ExperimentStatus.SUCCEEDED else "status-failed"
    )
    lineage = record.parent_experiment_id or record.reproduction_of or "—"
    integrity = (
        f'<div class="bad">Unreadable evidence: {escape(item.integrity_error)}</div>'
        if item.integrity_error
        else ""
    )
    return (
        "<tr>"
        f'<td><input type="checkbox" name="compare" value="{escape(record.experiment_id)}" aria-label="Compare {escape(record.experiment_id)}"></td>'
        f"<td>{escape(_short_timestamp(record.created_at))}</td>"
        f'<td><a href="/research/experiments?experiment={escape(record.experiment_id)}"><strong>{escape(record.name)}</strong></a><br><code>{escape(record.experiment_id)}</code>{integrity}</td>'
        f"<td>{escape(item.strategy_family or '—')}</td>"
        f"<td>{escape(record.mode.value)}</td>"
        f'<td class="{status_class}">{escape(record.status.value)}</td>'
        f"<td><code>{escape(record.dataset_version)}</code></td>"
        f"<td>{_result_glimpse(item.result)}</td>"
        f"<td>{escape(lineage)}</td>"
        "</tr>"
    )


def _render_detail(
    detail: ExperimentLibraryDetail,
    *,
    current_dataset_version: str | None,
) -> str:
    manifest = detail.manifest
    definition = manifest.definition
    stages = (
        "".join(
            f"<li><strong>{escape(stage.stage_name)}</strong> · checksum <code>{escape(stage.output_checksum)}</code> · {len(stage.warnings)} warning(s)</li>"
            for stage in manifest.stages
        )
        or "<li>No completed stage artifacts.</li>"
    )
    outputs = "".join(
        f"<details><summary>{escape(stage_name)} output</summary><pre>{escape(_pretty_json(payload))}</pre></details>"
        for stage_name, payload in detail.stage_outputs
    )
    lineage = (
        " → ".join(
            f'<a href="/research/experiments?experiment={escape(item.experiment_id)}">{escape(item.experiment_id)}</a>'
            for item in detail.lineage
        )
        or "—"
    )
    children = (
        "".join(
            f'<li><a href="/research/experiments?experiment={escape(item.experiment_id)}">{escape(item.name)} · {escape(item.experiment_id)}</a></li>'
            for item in detail.children
        )
        or "<li>None indexed.</li>"
    )
    rerun = _rerun_link(detail, current_dataset_version=current_dataset_version)
    failure = (
        '<div class="error"><strong>Recorded failure:</strong> '
        f"{escape(manifest.failure_type or 'UnknownError')}: "
        f"{escape(manifest.failure_message or '')}</div>"
        if manifest.status is ExperimentStatus.FAILED
        else ""
    )
    checksum = manifest.manifest_checksum or "missing"
    return f"""<div class="card" id="experiment-detail">
<h2>Experiment detail</h2>
<div class="grid">
  <div class="s6"><table>
    <tr><th>ID</th><td><code>{escape(manifest.experiment_id)}</code></td></tr>
    <tr><th>Name</th><td>{escape(definition.name)}</td></tr>
    <tr><th>Hypothesis</th><td>{escape(definition.hypothesis)}</td></tr>
    <tr><th>Mode</th><td>{escape(definition.mode.value)}</td></tr>
    <tr><th>Execution status</th><td>{escape(manifest.status.value)}</td></tr>
    <tr><th>Strategy family</th><td>{escape(detail.strategy_family or "—")}</td></tr>
    <tr><th>Dataset</th><td><code>{escape(definition.dataset_version)}</code></td></tr>
    <tr><th>Universe</th><td><code>{escape(definition.universe_version)}</code></td></tr>
    <tr><th>Code</th><td><code>{escape(definition.code_version)}</code></td></tr>
    <tr><th>Config schema</th><td><code>{escape(definition.config_schema_version)}</code></td></tr>
    <tr><th>Manifest checksum</th><td><code>{escape(checksum)}</code></td></tr>
  </table></div>
  <div class="s6"><h3>Result glimpse</h3>{_result_detail(detail.result)}<h3>Run lifecycle</h3><ul><li>Created: {escape(manifest.created_at)}</li><li>Started: {escape(manifest.started_at or "—")}</li><li>Completed: {escape(manifest.completed_at or "—")}</li><li>Warnings: {len(manifest.warnings)}</li></ul>{rerun}</div>
</div>
{failure}
<h3>Lineage</h3><div>{lineage}</div>
<h3>Direct children / reproductions</h3><ul>{children}</ul>
<h3>Resolved configuration</h3><pre>{escape(_pretty_json(definition.resolved_configuration))}</pre>
<h3>Stage artifacts</h3><ul>{stages}</ul>{outputs}
</div>"""


def _render_comparison(details: tuple[ExperimentLibraryDetail, ...]) -> str:
    headers = "".join(f"<th>{escape(item.manifest.experiment_id)}</th>" for item in details)
    result_rows = "".join(
        f"<tr><th>{escape(label)}</th>"
        + "".join(f"<td>{escape(value)}</td>" for value in values)
        + "</tr>"
        for label, values in _comparison_result_rows(details)
    )
    config_rows = "".join(
        f"<tr><th><code>{escape(path)}</code></th>"
        + "".join(f"<td><code>{escape(value)}</code></td>" for value in values)
        + "</tr>"
        for path, values in _configuration_diff(details)
    )
    if not config_rows:
        config_rows = (
            f'<tr><td colspan="{len(details) + 1}" class="subtle">'
            "Resolved configurations are identical.</td></tr>"
        )
    return f"""<div class="card" id="experiment-comparison">
<h2>Experiment comparison</h2>
<div class="banner"><strong>Descriptive comparison only.</strong> The library does not rank these experiments or turn multiple metrics into one score. Differences in dataset, code, sample and configuration remain visible.</div>
<div class="scroll"><table><thead><tr><th>Field</th>{headers}</tr></thead><tbody>{result_rows}</tbody></table></div>
<h3>Configuration differences</h3>
<div class="scroll"><table><thead><tr><th>Resolved configuration path</th>{headers}</tr></thead><tbody>{config_rows}</tbody></table></div>
</div>"""


def _comparison_result_rows(
    details: tuple[ExperimentLibraryDetail, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("Name", tuple(item.manifest.definition.name for item in details)),
        ("Status", tuple(item.manifest.status.value for item in details)),
        ("Mode", tuple(item.manifest.definition.mode.value for item in details)),
        ("Strategy family", tuple(item.strategy_family or "—" for item in details)),
        ("Dataset", tuple(item.manifest.definition.dataset_version for item in details)),
        ("Code", tuple(item.manifest.definition.code_version for item in details)),
        ("Result", tuple(_result_glimpse(item.result) for item in details)),
    )


def _configuration_diff(
    details: tuple[ExperimentLibraryDetail, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    flattened = tuple(
        _flatten_configuration(item.manifest.definition.resolved_configuration) for item in details
    )
    paths = sorted(set().union(*(set(item) for item in flattened)))
    rows: list[tuple[str, tuple[str, ...]]] = []
    for path in paths:
        values = tuple(item.get(path, "<missing>") for item in flattened)
        if len(set(values)) > 1:
            rows.append((path, values))
    return tuple(rows[:200])


def _flatten_configuration(
    value: dict[str, JSONValue],
    prefix: str = "",
) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in sorted(value.items()):
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten_configuration(item, path))
        else:
            result[path] = json.dumps(item, sort_keys=True, separators=(",", ":"))
    return result


def _rerun_link(
    detail: ExperimentLibraryDetail,
    *,
    current_dataset_version: str | None,
) -> str:
    manifest = detail.manifest
    if manifest.definition.dataset_version != current_dataset_version:
        return (
            '<div class="subtle">Re-run action unavailable because the workbench is not '
            "currently using this experiment's immutable dataset version.</div>"
        )
    query = _strategy_builder_query(manifest.definition.resolved_configuration)
    if query is None:
        return (
            '<div class="subtle">This experiment type cannot currently be restored into the '
            "Visual Strategy Builder.</div>"
        )
    return (
        '<div class="banner"><strong>Re-run with current code:</strong> this restores the saved '
        "Strategy Builder settings and starts a new EXPLORATORY experiment. It is not presented "
        "as an exact historical-code reproduction.</div>"
        f'<a class="button" href="/research/strategy?{escape(query)}">Re-run saved settings</a>'
    )


def _strategy_builder_query(configuration: dict[str, JSONValue]) -> str | None:
    if configuration.get("surface") != "visual_strategy_builder":
        return None
    universe = _mapping(configuration.get("universe"))
    outcome = _mapping(configuration.get("outcome"))
    entry = _mapping(configuration.get("entry"))
    selection = _mapping(configuration.get("selection"))
    exits = _mapping(configuration.get("exit_candidates"))
    costs = _mapping(configuration.get("execution_costs_bps"))
    if None in (universe, outcome, entry, selection, exits, costs):
        return None
    assert universe is not None
    assert outcome is not None
    assert entry is not None
    assert selection is not None
    assert exits is not None
    assert costs is not None
    params: list[tuple[str, str]] = [
        ("universe", str(universe.get("universe_id", "reviewed_canonical"))),
        ("entry_family", str(entry.get("family", "feature_expression"))),
        ("lookback_years", str(configuration.get("historical_lookback_years", 2))),
        ("horizon", str(outcome.get("maximum_holding_period_sessions", 20))),
        ("expression", str(entry.get("expression", ""))),
        ("rank_feature", str(selection.get("rank_feature", "return_20"))),
        (
            "rank_direction",
            "desc" if selection.get("rank_direction") == "descending" else "asc",
        ),
        ("per_session_limit", str(selection.get("per_session_limit", 500))),
        ("duration", str(entry.get("consolidation_duration_sessions", 20))),
        ("max_range_pct", str(entry.get("consolidation_max_range_percent", 12))),
        ("trend_filter", str(entry.get("trend_filter", "above_sma_50_100_200"))),
        (
            "volume_ratio",
            "none"
            if entry.get("minimum_breakout_volume_ratio") is None
            else str(entry.get("minimum_breakout_volume_ratio")),
        ),
        ("fixed_stops", _csv(exits.get("fixed_stop_percentages"))),
        ("trailing_stops", _csv(exits.get("trailing_stop_percentages"))),
        ("atr_stops", _csv(exits.get("atr_stop_multiples"))),
        ("trailing_atr", _csv(exits.get("trailing_atr_multiples"))),
        ("entry_slip", str(costs.get("entry_slippage", 0))),
        ("exit_slip", str(costs.get("normal_exit_slippage", 0))),
        ("stop_slip", str(costs.get("additional_stop_slippage", 0))),
        ("commission", str(costs.get("commission_per_side", 0))),
    ]
    variable = _mapping(configuration.get("research_variable"))
    if variable is not None and variable.get("kind") == "entry_parameter_sweep":
        values = variable.get("declared_values")
        if not isinstance(values, list) or not values:
            return None
        numeric: list[float] = []
        for value in values:
            if not isinstance(value, int | float) or isinstance(value, bool):
                return None
            numeric.append(float(value))
        step = numeric[1] - numeric[0] if len(numeric) > 1 else 1.0
        if step <= 0:
            return None
        params.extend(
            (
                ("entry_sweep_feature", str(variable.get("target_feature_name", ""))),
                ("entry_sweep_parameter", str(variable.get("parameter", ""))),
                ("entry_sweep_from", str(numeric[0])),
                ("entry_sweep_to", str(numeric[-1])),
                ("entry_sweep_step", str(step)),
            )
        )
    return urlencode(params)


def _mapping(value: JSONValue | None) -> dict[str, JSONValue] | None:
    return value if isinstance(value, dict) else None


def _csv(value: JSONValue | None) -> str:
    if not isinstance(value, list):
        return ""
    return ",".join(str(item) for item in value)


def _result_glimpse(result: ExperimentResultSummary | None) -> str:
    if result is None:
        return "—"
    if result.kind == "strategy_builder":
        return f"N={result.complete_event_count or 0} · hold {_pct(result.hold_expectancy)}"
    if result.kind == "strategy_builder_entry_sweep":
        return (
            f"{result.sweep_point_count or 0} cells · "
            f"{_pct(result.sweep_expectancy_low)} → {_pct(result.sweep_expectancy_high)}"
        )
    return result.kind


def _result_detail(result: ExperimentResultSummary | None) -> str:
    if result is None:
        return '<div class="subtle">No completed stage result is available.</div>'
    if result.kind == "strategy_builder":
        entry_count = result.entry_event_count if result.entry_event_count is not None else "—"
        complete_count = (
            result.complete_event_count if result.complete_event_count is not None else "—"
        )
        return (
            "<table>"
            f"<tr><th>Entry events</th><td>{entry_count}</td></tr>"
            f"<tr><th>Complete events</th><td>{complete_count}</td></tr>"
            f"<tr><th>Hold expectancy</th><td>{_pct(result.hold_expectancy)}</td></tr>"
            "</table>"
        )
    if result.kind == "strategy_builder_entry_sweep":
        return (
            "<table>"
            f"<tr><th>Declared cells</th><td>{result.sweep_point_count or 0}</td></tr>"
            f"<tr><th>Observed expectancy range</th><td>{_pct(result.sweep_expectancy_low)} → {_pct(result.sweep_expectancy_high)}</td></tr>"
            '</table><div class="subtle">The range is descriptive. The library does not treat '
            "the highest historical cell as a validated optimum.</div>"
        )
    return f"<div>{escape(result.kind)}</div>"


def _status_options(selected: ExperimentStatus | None) -> str:
    values = '<option value="">All</option>'
    for item in ExperimentStatus:
        values += _option(item.value, item.value, selected.value if selected is not None else None)
    return values


def _mode_options(selected: ResearchMode | None) -> str:
    values = '<option value="">All</option>'
    for item in ResearchMode:
        values += _option(item.value, item.value, selected.value if selected is not None else None)
    return values


def _option(value: str, label: str, selected: str | None) -> str:
    marker = " selected" if value == selected else ""
    return f'<option value="{escape(value)}"{marker}>{escape(label)}</option>'


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _short_timestamp(value: str) -> str:
    return value.replace("T", " ")[:19]


def _pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


__all__ = ["render_experiment_library_html"]
