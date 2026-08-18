# ruff: noqa: E501
"""Presentation-only HTML for research-brain creation, membership, and inspection."""

from __future__ import annotations

from html import escape

from trade_scout.app.research_brain_service import (
    ResearchBrainListItem,
    ResearchBrainView,
)
from trade_scout.experiments.research_brains import BrainAlignmentState


def render_research_brains_html(
    *,
    brains: tuple[ResearchBrainListItem, ...],
    detail: ResearchBrainView | None = None,
    prefill_experiment_id: str = "",
    message: str | None = None,
    error: str | None = None,
) -> str:
    """Render the brain UI while keeping all mutations as explicit POST forms."""

    brain_rows = "".join(_brain_row(item) for item in brains)
    if not brain_rows:
        brain_rows = '<tr><td colspan="7" class="subtle">No research brains exist yet.</td></tr>'
    options = "".join(
        f'<option value="{escape(item.definition.brain_id)}">{escape(item.definition.name)} · {escape(item.definition.brain_id)}</option>'
        for item in brains
    )
    message_html = f'<div class="success">{escape(message)}</div>' if message else ""
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    detail_html = _brain_detail(detail) if detail is not None else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Research Brains</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,96vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:14px 0 8px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s8 {{ grid-column:span 8; }} .s12 {{ grid-column:1/-1; }}
.banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin:14px 0; }} .success {{ border:1px solid #245a42; background:#0e2119; color:#9de2bd; padding:10px 12px; border-radius:8px; margin:14px 0; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:10px 12px; border-radius:8px; margin:14px 0; }}
label {{ display:grid; gap:5px; margin-bottom:10px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} input,select,textarea,button {{ width:100%; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:9px 10px; font:inherit; }} textarea {{ min-height:92px; resize:vertical; }} button,.button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.03em; }} .scroll {{ overflow:auto; }} code {{ color:#d9e3ef; }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:3px 7px; font-size:11px; font-weight:750; }} .in-scope {{ color:var(--good); }} .drift {{ color:var(--warn); }} .unassessed {{ color:var(--muted); }} .failed {{ color:var(--bad); }} ul {{ padding-left:20px; }} pre {{ margin:0; padding:10px; border:1px solid var(--border); border-radius:8px; background:#0c1118; overflow:auto; }}
@media(max-width:1000px) {{ .s4,.s6,.s8 {{ grid-column:1/-1; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/">← Research console</a> · <a href="/research/experiments">Experiment Library</a><h1>Research Brains</h1><div class="subtle">Focused, append-only research memory built from immutable experiment references.</div></div><span class="pill">NO AUTO-OPTIMIZATION</span></header>
<div class="banner"><strong>Brains preserve the whole research story.</strong> Successes, failures, nulls and adverse results stay in history. Focus drift produces a warning rather than deleting evidence. Conditioning remains NOT_ASSESSED until a separate evidence-sufficiency layer exists.</div>
{message_html}{error_html}
<div class="grid">
<div class="card s6"><h2>Create a research brain</h2><form method="post" action="/research/brains">
<input type="hidden" name="action" value="create">
<label>Brain ID<input name="brain_id" required placeholder="brain_entry_context"></label>
<label>Name<input name="name" required placeholder="Entry context research"></label>
<label>Research question<textarea name="research_question" required placeholder="Which related entry conditions add useful information beyond the baseline?"></textarea></label>
<label>Created by<input name="actor" required placeholder="researcher"></label>
<label>Optional focus rules<textarea name="focus_rules" placeholder="entry.family=feature_expression&#10;outcome.maximum_holding_period_sessions=20"></textarea><span class="subtle">One exact PATH=VALUE per line. Out-of-focus experiments can still be added; they receive DRIFT_WARNING.</span></label>
<label>Notes<textarea name="notes" placeholder="Why this question deserves a separate research memory..."></textarea></label>
<button type="submit">Create immutable brain</button>
</form></div>
<div class="card s6"><h2>Add an experiment</h2><form method="post" action="/research/brains">
<input type="hidden" name="action" value="add">
<label>Research brain<select name="brain_id" required><option value="">Choose brain...</option>{options}</select></label>
<label>Experiment ID<input name="experiment_id" required value="{escape(prefill_experiment_id)}" placeholder="exp_..."></label>
<label>Added by<input name="actor" required placeholder="researcher"></label>
<label>Membership note<textarea name="note" placeholder="Why this experiment belongs in this research question..."></textarea></label>
<button type="submit">Append experiment to brain</button>
</form><div class="banner"><strong>Mutation boundary:</strong> adding a membership is a POST action. Opening or filtering a page never changes brain history.</div></div>
</div>
<div class="card"><h2>Brain inventory</h2><div class="scroll"><table><thead><tr><th>Brain</th><th>Question</th><th>Experiments</th><th>Success</th><th>Failed</th><th>Drift</th><th>Conditioning</th></tr></thead><tbody>{brain_rows}</tbody></table></div></div>
{detail_html}
</div></body></html>"""


def _brain_row(item: ResearchBrainListItem) -> str:
    definition = item.definition
    return (
        "<tr>"
        f'<td><a href="/research/brains?brain={escape(definition.brain_id)}"><strong>{escape(definition.name)}</strong></a><br><code>{escape(definition.brain_id)}</code></td>'
        f"<td>{escape(definition.research_question)}</td>"
        f"<td>{item.membership_count}</td>"
        f"<td>{item.succeeded_count}</td>"
        f'<td class="failed">{item.failed_count}</td>'
        f'<td class="drift">{item.drift_warning_count}</td>'
        f"<td>{escape(item.conditioning_readiness)}</td>"
        "</tr>"
    )


def _brain_detail(view: ResearchBrainView) -> str:
    snapshot = view.snapshot
    definition = snapshot.definition
    focus = "".join(
        f"<li><code>{escape(rule.configuration_path)}</code> ∈ {escape(repr(rule.allowed_values))} — {escape(rule.rationale)}</li>"
        for rule in definition.focus_rules
    ) or "<li>No explicit focus rules. New memberships are UNASSESSED rather than assumed in-scope.</li>"
    experiment_rows = "".join(_experiment_row(item) for item in view.experiments)
    if not experiment_rows:
        experiment_rows = '<tr><td colspan="7" class="subtle">No experiments have been added to this brain.</td></tr>'
    return f"""<div class="card" id="brain-detail"><h2>{escape(definition.name)}</h2>
<div class="grid"><div class="s8"><table>
<tr><th>Brain ID</th><td><code>{escape(definition.brain_id)}</code></td></tr>
<tr><th>Research question</th><td>{escape(definition.research_question)}</td></tr>
<tr><th>Created by</th><td>{escape(definition.created_by)}</td></tr>
<tr><th>Created at</th><td>{escape(definition.created_at)}</td></tr>
<tr><th>Notes</th><td>{escape(definition.notes or '—')}</td></tr>
</table></div><div class="s4"><h3>Inventory</h3><ul><li>{len(snapshot.memberships)} memberships</li><li>{snapshot.succeeded_count} succeeded</li><li>{snapshot.failed_count} failed</li><li>{snapshot.in_scope_count} in scope</li><li>{snapshot.drift_warning_count} drift warnings</li><li>{snapshot.unassessed_count} unassessed</li></ul><strong>Conditioning: {escape(snapshot.conditioning_readiness)}</strong><div class="subtle">{escape(snapshot.conditioning_note)}</div></div></div>
<h3>Focus envelope</h3><ul>{focus}</ul>
<h3>Preserved experiments</h3><div class="scroll"><table><thead><tr><th>Added</th><th>Experiment</th><th>Execution</th><th>Alignment</th><th>Result / evidence</th><th>Membership note</th><th>Integrity</th></tr></thead><tbody>{experiment_rows}</tbody></table></div>
</div>"""


def _experiment_row(item: object) -> str:
    from trade_scout.app.research_brain_service import ResearchBrainExperimentView

    if not isinstance(item, ResearchBrainExperimentView):
        raise TypeError("unexpected research-brain experiment view")
    membership = item.membership
    alignment_class = {
        BrainAlignmentState.IN_SCOPE: "in-scope",
        BrainAlignmentState.DRIFT_WARNING: "drift",
        BrainAlignmentState.UNASSESSED: "unassessed",
    }[membership.alignment_state]
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in membership.alignment_reasons)
    reason_html = f"<ul>{reasons}</ul>" if reasons else ""
    if item.experiment is None:
        experiment_name = membership.experiment_id
        result = "—"
    else:
        experiment_name = item.experiment.manifest.definition.name
        result = _result_text(item.experiment)
    integrity = escape(item.integrity_error) if item.integrity_error else "verified"
    return (
        "<tr>"
        f"<td>{escape(membership.added_at)}</td>"
        f'<td><a href="/research/experiments?experiment={escape(membership.experiment_id)}"><strong>{escape(experiment_name)}</strong></a><br><code>{escape(membership.experiment_id)}</code></td>'
        f"<td>{escape(membership.experiment_status.value)}</td>"
        f'<td class="{alignment_class}">{escape(membership.alignment_state.value)}{reason_html}</td>'
        f"<td>{escape(result)}</td>"
        f"<td>{escape(membership.note or '—')}</td>"
        f"<td>{integrity}</td>"
        "</tr>"
    )


def _result_text(detail: object) -> str:
    from trade_scout.app.experiment_library_service import ExperimentLibraryDetail

    if not isinstance(detail, ExperimentLibraryDetail) or detail.result is None:
        return "No completed result summary"
    result = detail.result
    if result.kind == "strategy_builder":
        expectancy = "—" if result.hold_expectancy is None else f"{result.hold_expectancy * 100:+.2f}%"
        return f"N={result.complete_event_count or 0}; hold expectancy {expectancy}"
    if result.kind == "strategy_builder_entry_sweep":
        low = "—" if result.sweep_expectancy_low is None else f"{result.sweep_expectancy_low * 100:+.2f}%"
        high = "—" if result.sweep_expectancy_high is None else f"{result.sweep_expectancy_high * 100:+.2f}%"
        return f"{result.sweep_point_count or 0} cells; expectancy {low} to {high}"
    return result.kind


__all__ = ["render_research_brains_html"]
