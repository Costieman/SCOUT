# ruff: noqa: E501
"""Presentation-only HTML for research-brain creation, membership, and inspection."""

from __future__ import annotations

from html import escape

from trade_scout.app.research_brain_checkpoints import ResearchBrainReviewCheckpoint
from trade_scout.app.research_brain_review import (
    ResearchBrainReview,
    build_research_brain_review,
)
from trade_scout.app.research_brain_service import (
    ResearchBrainExperimentView,
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
        brain_rows = '<tr><td colspan="7" class="subtle">No research brains yet. Create one above when you have a research question you want SCOUT to remember.</td></tr>'
    options = "".join(
        f'<option value="{escape(item.definition.brain_id)}">{escape(item.definition.name)}</option>'
        for item in brains
    )
    message_html = f'<div class="success">{escape(message)}</div>' if message else ""
    error_html = (
        f'<div class="error"><strong>Could not complete that action:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    detail_html = _brain_detail(detail) if detail is not None else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Research Brains</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,96vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:14px 0 8px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s8 {{ grid-column:span 8; }}
.banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin:14px 0; }} .success {{ border:1px solid #245a42; background:#0e2119; color:#9de2bd; padding:10px 12px; border-radius:8px; margin:14px 0; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:10px 12px; border-radius:8px; margin:14px 0; }} .review {{ border:1px solid #665a2d; background:#17140b; padding:14px; border-radius:10px; margin-top:18px; }} .review-columns {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }} .review-box {{ border:1px solid var(--border); border-radius:8px; padding:12px; background:#0f141c; }} .checkpoint {{ border-top:1px solid var(--border); margin-top:14px; padding-top:14px; }} .checkpoint-form {{ display:grid; grid-template-columns:1fr 2fr auto; gap:10px; align-items:end; margin-top:10px; }}
label {{ display:grid; gap:5px; margin-bottom:10px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} input,select,textarea,button {{ width:100%; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:9px 10px; font:inherit; }} textarea {{ min-height:92px; resize:vertical; }} button,.button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.03em; }} .scroll {{ overflow:auto; }} code {{ color:#d9e3ef; }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:3px 7px; font-size:11px; font-weight:750; }} .in-scope {{ color:var(--good); }} .drift {{ color:var(--warn); }} .unassessed {{ color:var(--muted); }} .failed {{ color:var(--bad); }} ul {{ padding-left:20px; }} details {{ margin:12px 0; }} summary {{ cursor:pointer; color:var(--accent); font-weight:700; }} .plain-state {{ display:block; margin-top:4px; color:var(--muted); font-size:12px; }}
@media(max-width:1000px) {{ .s4,.s6,.s8 {{ grid-column:1/-1; }} .review-columns,.checkpoint-form {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/">← Research console</a> · <a href="/research/experiments">Experiment Library</a><h1>Research Brains</h1><div class="subtle">A brain is a saved research question. It remembers every experiment you attach, including the ones that did not work.</div></div><span class="pill">RESEARCH MEMORY</span></header>
<div class="banner"><strong>Nothing is automatically optimized here.</strong> A brain keeps the full research history so future summaries can learn from both positive and negative evidence. If an experiment drifts away from the brain's stated focus, SCOUT keeps it but shows a scope warning.</div>
{message_html}{error_html}
<div class="grid">
<div class="card s6"><h2>Start a new research brain</h2><div class="subtle">Use a plain-English question. SCOUT creates the technical brain ID automatically.</div><form method="post" action="/research/brains">
<input type="hidden" name="action" value="create">
<label>Name<input name="name" required placeholder="Volatility and trend entries"></label>
<label>What are you trying to learn?<textarea name="research_question" required placeholder="Does lower pre-entry volatility improve returns when the stock is already in a strong trend?"></textarea></label>
<label>Researcher<input name="actor" required value="local-user"></label>
<details><summary>Advanced: keep this brain tightly focused</summary><div class="subtle">Optional. Add one exact setting per line. If a future experiment falls outside these boundaries, SCOUT will keep it and show a warning rather than deleting it.</div><label>Focus boundaries<textarea name="focus_rules" placeholder="entry.family=feature_expression&#10;outcome.maximum_holding_period_sessions=20"></textarea></label></details>
<label>Notes<textarea name="notes" placeholder="Anything useful to remember about why this question matters..."></textarea></label>
<button type="submit">Create research brain</button>
</form></div>
<div class="card s6"><h2>Add a saved experiment</h2><div class="subtle">Attach an existing experiment record to a brain. This does not rerun or change the experiment.</div><form method="post" action="/research/brains">
<input type="hidden" name="action" value="add">
<label>Research brain<select name="brain_id" required><option value="">Choose a brain...</option>{options}</select></label>
<label>Experiment ID<input name="experiment_id" required value="{escape(prefill_experiment_id)}" placeholder="exp_..."></label>
<label>Researcher<input name="actor" required value="local-user"></label>
<label>Why does this experiment belong here?<textarea name="note" placeholder="For example: first volatility-period sweep in this research thread."></textarea></label>
<button type="submit">Add experiment to brain</button>
</form><div class="banner"><strong>Safe history:</strong> opening, filtering, or reading a brain never changes it. Adding an experiment is an explicit action.</div></div>
</div>
<div class="card"><h2>Your research brains</h2><div class="scroll"><table><thead><tr><th>Brain</th><th>Question</th><th>Experiments</th><th>Successful runs</th><th>Failed runs</th><th>Scope warnings</th><th>Brain summary</th></tr></thead><tbody>{brain_rows}</tbody></table></div></div>
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
        f"<td>{_conditioning_label(item.conditioning_readiness)}</td>"
        "</tr>"
    )


def _brain_detail(view: ResearchBrainView) -> str:
    snapshot = view.snapshot
    definition = snapshot.definition
    review = build_research_brain_review(snapshot, view.experiments)
    focus = (
        "".join(
            f"<li><code>{escape(rule.configuration_path)}</code> must be one of {escape(repr(rule.allowed_values))}</li>"
            for rule in definition.focus_rules
        )
        or "<li>No strict focus boundaries were set. SCOUT will preserve experiments without trying to classify them as in or out of scope.</li>"
    )
    experiment_rows = "".join(_experiment_row(item) for item in view.experiments)
    if not experiment_rows:
        experiment_rows = '<tr><td colspan="7" class="subtle">No experiments have been added to this brain yet.</td></tr>'
    return f"""<div class="card" id="brain-detail"><h2>{escape(definition.name)}</h2>
<div class="grid"><div class="s8"><table>
<tr><th>Research question</th><td>{escape(definition.research_question)}</td></tr>
<tr><th>Created by</th><td>{escape(definition.created_by)}</td></tr>
<tr><th>Created at</th><td>{escape(definition.created_at)}</td></tr>
<tr><th>Notes</th><td>{escape(definition.notes or "—")}</td></tr>
<tr><th>Technical brain ID</th><td><code>{escape(definition.brain_id)}</code></td></tr>
</table></div><div class="s4"><h3>What is in this brain?</h3><ul><li>{len(snapshot.memberships)} saved experiments</li><li>{snapshot.succeeded_count} successful runs</li><li>{snapshot.failed_count} failed runs retained</li><li>{snapshot.in_scope_count} match the declared focus</li><li>{snapshot.drift_warning_count} scope warnings</li><li>{snapshot.unassessed_count} not scope-classified</li></ul><strong>Brain summary: {_conditioning_label(snapshot.conditioning_readiness)}</strong><div class="subtle">{escape(snapshot.conditioning_note)}</div></div></div>
{_review_section(review, definition.brain_id, view.review_checkpoints)}
<details><summary>Advanced: focus boundaries</summary><ul>{focus}</ul></details>
<h3>Experiments remembered by this brain</h3><div class="scroll"><table><thead><tr><th>Added</th><th>Experiment</th><th>Run status</th><th>Fits this brain?</th><th>Result glimpse</th><th>Your note</th><th>Evidence check</th></tr></thead><tbody>{experiment_rows}</tbody></table></div>
</div>"""


def _review_section(
    review: ResearchBrainReview,
    brain_id: str,
    checkpoints: tuple[ResearchBrainReviewCheckpoint, ...],
) -> str:
    findings = _review_list(review.findings, "No findings yet; add experiment evidence first.")
    cautions = _review_list(review.cautions, "No additional cautions recorded.")
    next_questions = _review_list(review.next_questions, "No follow-up question is available yet.")
    history = _checkpoint_history(checkpoints)
    return f"""<div class="review"><h3>Brain review — what the saved evidence currently says</h3>
<div class="banner"><strong>{escape(_review_readiness_label(review.readiness_label))}</strong><br>{escape(review.readiness_explanation)}<br><span class="subtle">This is a descriptive evidence review, not validation, optimization, or a trading recommendation.</span></div>
<div class="review-columns"><div class="review-box"><strong>What we can say</strong>{findings}</div><div class="review-box"><strong>What is still shaky</strong>{cautions}</div><div class="review-box"><strong>Useful next questions</strong>{next_questions}</div></div>
<div class="checkpoint"><strong>Freeze this review as a checkpoint</strong><div class="subtle">A checkpoint records this exact descriptive review and the exact experiments currently in the brain. It does not rerun research, choose winners, or validate anything. Later checkpoints let us see how the brain's evidence changed over time.</div>
<form class="checkpoint-form" method="post" action="/research/brains"><input type="hidden" name="action" value="checkpoint"><input type="hidden" name="brain_id" value="{escape(brain_id)}"><label>Researcher<input name="actor" required value="local-user"></label><label>Optional note<input name="note" placeholder="For example: first volatility review before follow-up comparator tests"></label><button type="submit">Save review checkpoint</button></form>
{history}</div>
</div>"""


def _checkpoint_history(checkpoints: tuple[ResearchBrainReviewCheckpoint, ...]) -> str:
    if not checkpoints:
        return '<div class="subtle">No review checkpoints saved yet.</div>'
    rows = "".join(
        "<tr>"
        f"<td>{escape(_short_timestamp(item.created_at))}</td>"
        f"<td><code>{escape(item.checkpoint_id)}</code></td>"
        f"<td>{len(item.memberships)}</td>"
        f"<td>{escape(_review_readiness_label(item.review.readiness_label))}</td>"
        f"<td>{escape(item.created_by)}</td>"
        f"<td>{escape(item.note or '—')}</td>"
        "</tr>"
        for item in reversed(checkpoints)
    )
    return f'<h3>Saved review checkpoints</h3><div class="scroll"><table><thead><tr><th>Saved</th><th>Checkpoint</th><th>Experiments</th><th>Review state</th><th>Researcher</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table></div>'


def _review_list(items: tuple[str, ...], empty: str) -> str:
    values = items or (empty,)
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in values) + "</ul>"


def _review_readiness_label(value: str) -> str:
    labels = {
        "EMPTY": "No evidence yet",
        "EVIDENCE_CHECK_NEEDED": "Evidence check needed",
        "FAILURE_HISTORY_ONLY": "Failure history captured",
        "BASIC_REVIEW_AVAILABLE": "Basic descriptive review available",
        "DESCRIPTIVE_REVIEW_AVAILABLE": "Structured descriptive review available",
    }
    return labels.get(value, value.replace("_", " ").title())


def _experiment_row(item: ResearchBrainExperimentView) -> str:
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
    integrity = escape(item.integrity_error) if item.integrity_error else "Verified"
    return (
        "<tr>"
        f"<td>{escape(_short_timestamp(membership.added_at))}</td>"
        f'<td><a href="/research/experiments?experiment={escape(membership.experiment_id)}"><strong>{escape(experiment_name)}</strong></a><br><code>{escape(membership.experiment_id)}</code></td>'
        f"<td>{escape(membership.experiment_status.value)}</td>"
        f'<td class="{alignment_class}">{_alignment_label(membership.alignment_state)}{reason_html}</td>'
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
        expectancy = (
            "—" if result.hold_expectancy is None else f"{result.hold_expectancy * 100:+.2f}%"
        )
        return f"N={result.complete_event_count or 0}; hold expectancy {expectancy}"
    if result.kind == "strategy_builder_entry_sweep":
        low = (
            "—"
            if result.sweep_expectancy_low is None
            else f"{result.sweep_expectancy_low * 100:+.2f}%"
        )
        high = (
            "—"
            if result.sweep_expectancy_high is None
            else f"{result.sweep_expectancy_high * 100:+.2f}%"
        )
        return f"{result.sweep_point_count or 0} tested values; expectancy {low} to {high}"
    return result.kind


def _alignment_label(state: BrainAlignmentState) -> str:
    if state is BrainAlignmentState.IN_SCOPE:
        return 'Yes<span class="plain-state">IN_SCOPE</span>'
    if state is BrainAlignmentState.DRIFT_WARNING:
        return 'Scope warning<span class="plain-state">DRIFT_WARNING — kept in history</span>'
    return 'Not checked<span class="plain-state">UNASSESSED</span>'


def _conditioning_label(value: str) -> str:
    return "Not conditioned yet" if value == "NOT_ASSESSED" else escape(value)


def _short_timestamp(value: str) -> str:
    return value.replace("T", " ")[:19]


__all__ = ["render_research_brains_html"]
