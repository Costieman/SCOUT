# ruff: noqa: E501
"""Presentation-only HTML for research-brain creation, membership, and inspection."""

from __future__ import annotations

from html import escape

from trade_scout.app.research_brain_checkpoints import ResearchBrainReviewCheckpoint
from trade_scout.app.research_brain_conditioning import (
    ConditioningDimension,
    ConditioningState,
    ResearchBrainConditioning,
    build_research_brain_conditioning,
)
from trade_scout.app.research_brain_followup_execution import ResearchBrainFollowUpExecution
from trade_scout.app.research_brain_followups import FollowUpKind, ResearchBrainFollowUpView
from trade_scout.app.research_brain_review import (
    ResearchBrainReview,
    build_research_brain_review,
)
from trade_scout.app.research_brain_service import (
    ResearchBrainExperimentView,
    ResearchBrainListItem,
    ResearchBrainView,
)
from trade_scout.app.strategy_builder_configuration import source_declared_entry_sweep_values
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
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,96vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:14px 0 8px; }} h4 {{ margin:12px 0 6px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s8 {{ grid-column:span 8; }}
.banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin:14px 0; }} .success {{ border:1px solid #245a42; background:#0e2119; color:#9de2bd; padding:10px 12px; border-radius:8px; margin:14px 0; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:10px 12px; border-radius:8px; margin:14px 0; }} .review {{ border:1px solid #665a2d; background:#17140b; padding:14px; border-radius:10px; margin-top:18px; }} .review-columns {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }} .review-box {{ border:1px solid var(--border); border-radius:8px; padding:12px; background:#0f141c; }} .checkpoint {{ border-top:1px solid var(--border); margin-top:14px; padding-top:14px; }} .checkpoint-form {{ display:grid; grid-template-columns:1fr 2fr auto; gap:10px; align-items:end; margin-top:10px; }}
.conditioning {{ border:1px solid #31526a; background:#0d1720; padding:14px; border-radius:10px; margin-top:18px; }} .condition-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:12px; }} .condition-card {{ border:1px solid var(--border); border-radius:8px; padding:12px; background:#0d131b; min-width:0; }} .condition-card h4 {{ margin:0 0 6px; font-size:14px; }} .condition-state {{ display:inline-block; margin-bottom:8px; font-size:11px; font-weight:800; letter-spacing:.04em; }} .state-available {{ color:var(--good); }} .state-partial {{ color:var(--warn); }} .state-missing {{ color:#f0a2a2; }} .state-check-needed {{ color:var(--bad); }} .state-not-applicable {{ color:var(--muted); }} .priority {{ border:1px solid #665a2d; background:#1b170c; padding:12px; border-radius:8px; margin-top:12px; }}
.followups {{ border:1px solid #3d4f75; background:#101521; padding:14px; border-radius:10px; margin-top:18px; }} .followup-card {{ border:1px solid var(--border); background:#0d121b; border-radius:9px; padding:13px; margin-top:12px; }} .followup-status {{ display:inline-block; font-size:11px; font-weight:850; letter-spacing:.04em; margin:4px 0 10px; }} .followup-draft {{ color:var(--warn); }} .followup-approved {{ color:var(--good); }} .followup-stale {{ color:var(--bad); }} .followup-executed {{ color:var(--blue); }} .followup-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }} .followup-actions {{ display:grid; grid-template-columns:1fr 2fr auto; gap:10px; align-items:end; margin-top:12px; }} .execution-box {{ border:1px solid #32604d; background:#0d1c17; border-radius:8px; padding:12px; margin-top:12px; }} .execution-form {{ display:grid; grid-template-columns:1fr 1fr auto; gap:10px; align-items:end; margin-top:10px; }}
label {{ display:grid; gap:5px; margin-bottom:10px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} input,select,textarea,button {{ width:100%; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:9px 10px; font:inherit; }} textarea {{ min-height:92px; resize:vertical; }} button,.button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.03em; }} .scroll {{ overflow:auto; }} code {{ color:#d9e3ef; }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:3px 7px; font-size:11px; font-weight:750; }} .in-scope {{ color:var(--good); }} .drift {{ color:var(--warn); }} .unassessed {{ color:var(--muted); }} .failed {{ color:var(--bad); }} ul {{ padding-left:20px; }} details {{ margin:12px 0; }} summary {{ cursor:pointer; color:var(--accent); font-weight:700; }} .plain-state {{ display:block; margin-top:4px; color:var(--muted); font-size:12px; }}
@media(max-width:1100px) {{ .condition-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }} @media(max-width:1000px) {{ .s4,.s6,.s8 {{ grid-column:1/-1; }} .review-columns,.checkpoint-form,.condition-grid,.followup-grid,.followup-actions,.execution-form {{ grid-template-columns:1fr; }} }}
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
    conditioning = build_research_brain_conditioning(view)
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
{_conditioning_section(conditioning)}
{_follow_up_section(view, conditioning)}
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


def _conditioning_section(conditioning: ResearchBrainConditioning) -> str:
    cards = "".join(_conditioning_card(item) for item in conditioning.dimensions)
    return f"""<div class="conditioning"><h3>Brain conditioning — evidence quality map</h3>
<div class="banner"><strong>No overall score.</strong> SCOUT checks each evidence dimension separately so a large raw return cannot hide a missing comparator, tiny sample, absent uncertainty, or lack of unseen-data testing.<br><span class="subtle">{escape(conditioning.boundary)}</span></div>
<div class="condition-grid">{cards}</div>
<div class="priority"><strong>{escape(conditioning.priority_title)}</strong><br>{escape(conditioning.priority_action)}</div>
</div>"""


def _conditioning_card(item: ConditioningDimension) -> str:
    evidence = ""
    if item.evidence:
        evidence = (
            "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in item.evidence) + "</ul>"
        )
    next_step = (
        f'<div class="subtle"><strong>What would improve this:</strong> {escape(item.next_step)}</div>'
        if item.next_step
        else ""
    )
    state_class = f"state-{item.state.value.casefold().replace('_', '-')}"
    return (
        '<div class="condition-card">'
        f"<h4>{escape(item.label)}</h4>"
        f'<span class="condition-state {state_class}">{escape(_conditioning_state_label(item.state))}</span>'
        f"<div>{escape(item.summary)}</div>{evidence}{next_step}"
        "</div>"
    )


def _follow_up_section(
    view: ResearchBrainView,
    conditioning: ResearchBrainConditioning,
) -> str:
    executions = {item.proposal_id: item for item in view.follow_up_executions}
    proposals = "".join(
        _follow_up_card(item, view, executions.get(item.proposal.proposal_id))
        for item in reversed(view.follow_up_proposals)
    )
    if not proposals:
        proposals = (
            '<div class="subtle">No follow-up proposal has been drafted for this brain yet.</div>'
        )
    if view.snapshot.succeeded_count:
        draft = f"""<form class="followup-actions" method="post" action="/research/brains"><input type="hidden" name="action" value="draft_follow_up"><input type="hidden" name="brain_id" value="{escape(view.snapshot.definition.brain_id)}"><label>Researcher<input name="actor" required value="local-user"></label><div class="subtle">SCOUT will freeze the current priority, source experiment and brain evidence state into a proposal. It will not run the proposal.</div><button type="submit">Draft next experiment</button></form>"""
    else:
        draft = '<div class="subtle">A proposal needs at least one readable successful experiment as its frozen source.</div>'
    return f"""<div class="followups"><h3>Proposed next experiment — approval and execution gates</h3>
<div class="banner"><strong>Three separate steps:</strong> SCOUT drafts a frozen plan; you approve that exact plan; only then can an implemented executor run it. Execution is another explicit click and creates a normal governed child experiment. Unsupported proposal types stay approval-only rather than being approximated.</div>
<div><strong>Current conditioning priority:</strong> {escape(conditioning.priority_title)}<br>{escape(conditioning.priority_action)}</div>
{draft}
<h3>Follow-up proposal history</h3>{proposals}
</div>"""


def _follow_up_card(
    item: ResearchBrainFollowUpView,
    view: ResearchBrainView,
    execution: ResearchBrainFollowUpExecution | None,
) -> str:
    proposal = item.proposal
    if execution is not None:
        status_class = "followup-executed"
        status_label = (
            "Executed — result succeeded"
            if execution.result_status.value == "SUCCEEDED"
            else "Executed — result failed and was retained"
        )
    else:
        status = item.status
        status_class = {
            "DRAFT": "followup-draft",
            "APPROVED_NOT_RUN": "followup-approved",
            "STALE": "followup-stale",
        }[status]
        status_label = {
            "DRAFT": "Draft — awaiting your approval",
            "APPROVED_NOT_RUN": "Approved — not run",
            "STALE": "Stale — brain evidence changed",
        }[status]
    frozen = (
        "<ul>"
        + "".join(f"<li>{escape(value)}</li>" for value in proposal.frozen_elements)
        + "</ul>"
    )
    required = (
        "<ul>"
        + "".join(f"<li>{escape(value)}</li>" for value in proposal.required_operator_inputs)
        + "</ul>"
        if proposal.required_operator_inputs
        else '<div class="subtle">No additional scientific input is required to preserve this proposal as a plan.</div>'
    )
    action = _follow_up_action(item, view, execution)
    return f"""<div class="followup-card"><strong>{escape(proposal.title)}</strong><br><span class="followup-status {status_class}">{escape(status_label)}</span>
<div class="followup-grid"><div><strong>Hypothesis</strong><div>{escape(proposal.hypothesis)}</div><h4>Keep fixed</h4>{frozen}</div><div><strong>Change only this</strong><div>{escape(proposal.proposed_change)}</div><h4>Still needs your input</h4>{required}</div></div>
<div class="banner"><strong>Why SCOUT suggested this:</strong> {escape(proposal.rationale)}<br><strong>Source experiment:</strong> <a href="/research/experiments?experiment={escape(proposal.source_experiment_id)}">{escape(proposal.source_experiment_id)}</a><br><strong>Plan readiness:</strong> {escape(proposal.readiness.value.replace("_", " ").title())}<br><span class="subtle">{escape(proposal.execution_boundary)}</span></div>
<div class="subtle">Proposal ID: <code>{escape(proposal.proposal_id)}</code> · drafted {escape(_short_timestamp(proposal.created_at))}</div>{action}
</div>"""


def _follow_up_action(
    item: ResearchBrainFollowUpView,
    view: ResearchBrainView,
    execution: ResearchBrainFollowUpExecution | None,
) -> str:
    proposal = item.proposal
    if execution is not None:
        status_text = execution.result_status.value.replace("_", " ").title()
        return f"""<div class="execution-box"><strong>Execution receipt</strong><br>Result status: {escape(status_text)}<br>Result experiment: <a href="/research/experiments?experiment={escape(execution.result_experiment_id)}">{escape(execution.result_experiment_id)}</a><br><span class="subtle">Executed by {escape(execution.executed_by)} at {escape(_short_timestamp(execution.executed_at))}. The terminal child experiment was automatically appended to this brain. Proposal execution ID: <code>{escape(execution.execution_id)}</code></span></div>"""
    if item.stale:
        return '<div class="error"><strong>This version is stale.</strong> The brain changed after this plan was drafted. Draft a fresh proposal; stale approval is never reused for execution.</div>'
    if item.approval is None:
        return f"""<form class="followup-actions" method="post" action="/research/brains"><input type="hidden" name="action" value="approve_follow_up"><input type="hidden" name="brain_id" value="{escape(proposal.brain_id)}"><input type="hidden" name="proposal_id" value="{escape(proposal.proposal_id)}"><label>Researcher<input name="actor" required value="local-user"></label><label>Approval note<input name="note" placeholder="Why this is the right next evidence challenge"></label><button type="submit">Approve plan — do not run</button></form>"""

    approval_note = f" Note: {escape(item.approval.note)}" if item.approval.note else ""
    approved = f'<div class="success"><strong>Approved by {escape(item.approval.approved_by)}</strong> at {escape(_short_timestamp(item.approval.approved_at))}. Approval alone did not run research.{approval_note}</div>'
    if proposal.kind is not FollowUpKind.COMPARATOR:
        return approved + (
            '<div class="banner"><strong>Execution adapter not implemented for this challenge yet.</strong> '
            "SCOUT will not substitute a nearby test. The approval remains preserved until a dedicated "
            "executor can honor this exact research question.</div>"
        )

    source_detail = next(
        (
            experiment.experiment
            for experiment in view.experiments
            if experiment.experiment is not None
            and experiment.experiment.manifest.experiment_id == proposal.source_experiment_id
        ),
        None,
    )
    declared = (
        source_declared_entry_sweep_values(source_detail.manifest.definition.resolved_configuration)
        if source_detail is not None
        else ()
    )
    candidate = ""
    if declared:
        options = "".join(f'<option value="{value:g}">{value:g}</option>' for value in declared)
        candidate = f"""<label>Freeze one source-sweep candidate<select name="candidate_value" required><option value="">Choose a value...</option>{options}</select><span class="subtle">SCOUT does not select the historical maximum for you. The chosen value must already be in the saved sweep.</span></label>"""
    else:
        candidate = '<input type="hidden" name="candidate_value" value="">'
    form = f"""<div class="execution-box"><strong>Executable comparator v1</strong><div class="subtle">This runs a count-matched same-instrument randomized eligible-timing control on the frozen feature-expression definition. It uses 1,000 deterministic randomizations, the same holding horizon and execution costs, makes no provider calls, writes a child experiment, and automatically adds the terminal result back to this brain. This is exploratory comparator evidence, not validation.</div>
<form class="execution-form" method="post" action="/research/brains"><input type="hidden" name="action" value="execute_follow_up_comparator"><input type="hidden" name="brain_id" value="{escape(proposal.brain_id)}"><input type="hidden" name="proposal_id" value="{escape(proposal.proposal_id)}"><label>Researcher<input name="actor" required value="local-user"></label>{candidate}<button type="submit">Run approved comparator</button></form></div>"""
    return approved + form


def _conditioning_state_label(state: ConditioningState) -> str:
    labels = {
        ConditioningState.AVAILABLE: "Evidence found",
        ConditioningState.PARTIAL: "Needs caution",
        ConditioningState.MISSING: "Not found / not tested",
        ConditioningState.CHECK_NEEDED: "Evidence check needed",
        ConditioningState.NOT_APPLICABLE: "Not applicable yet",
    }
    return labels[state]


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
    if result.kind == "research_brain_random_timing_comparator":
        return "Randomized eligible-timing comparator evidence"
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
