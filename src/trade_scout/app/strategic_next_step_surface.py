# ruff: noqa: E501
"""Shared presentation for deterministic strategic next-step analyses."""

from __future__ import annotations

from html import escape
from typing import Protocol

from trade_scout.app.strategic_followup import StrategicFollowupPlan


class StrategicOptionLike(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def direction(self) -> str: ...

    @property
    def proposed_range(self) -> str: ...

    @property
    def rationale(self) -> str: ...

    @property
    def falsifier(self) -> str: ...


class StrategicAnalysisLike(Protocol):
    @property
    def headline(self) -> str: ...

    @property
    def observation(self) -> str: ...

    @property
    def robustness(self) -> str: ...

    @property
    def caution(self) -> str: ...

    @property
    def options(self) -> tuple[StrategicOptionLike, ...]: ...


def render_strategic_next_step_html(
    analysis: StrategicAnalysisLike,
    followup: StrategicFollowupPlan | None = None,
) -> str:
    """Render the same operator-controlled analysis popup for exit and entry sweeps."""

    options = "".join(
        f"""<article class="strategic-option">
        <h3>{escape(item.title)}</h3>
        <p><strong>Direction:</strong> {escape(item.direction)}</p>
        <p><strong>Suggested next range:</strong> {escape(item.proposed_range)}</p>
        <p><strong>Why:</strong> {escape(item.rationale)}</p>
        <p><strong>What would falsify it:</strong> {escape(item.falsifier)}</p>
        </article>"""
        for item in analysis.options
    )
    if followup is not None and not followup.can_run:
        options = '<p class="subtle">No further expectancy-honing sweep is recommended for this variable.</p>'
    elif not options:
        options = '<p class="subtle">No directional parameter experiment can be inferred safely from this run yet.</p>'
    robustness = (
        escape(analysis.robustness)
        if analysis.robustness
        else "No separate robustness statement is available for this result."
    )
    followup_html = _render_followup(followup)
    return f"""
<style id="strategic-next-step-style">
body.strategic-next-step-modal-open {{ overflow:hidden; }}
.strategic-next-step-summary {{ border-color:#6d5b24 !important; background:linear-gradient(135deg,#17170f,#121720) !important; }}
.strategic-next-step-summary .toolbar {{ margin-top:12px; }}
.strategic-next-step-overlay {{ position:fixed; inset:0; z-index:5000; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(3,6,10,.78); backdrop-filter:blur(4px); }}
.strategic-next-step-overlay[hidden] {{ display:none; }}
.strategic-next-step-dialog {{ width:min(960px,96vw); max-height:88vh; overflow:auto; border:1px solid #6d5b24; border-radius:14px; background:#121720; box-shadow:0 28px 80px rgba(0,0,0,.5); padding:20px; }}
.strategic-next-step-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }}
.strategic-next-step-head button {{ flex:0 0 auto; }}
.strategic-next-step-observation {{ border-left:3px solid #7fc8ff; background:#10151d; padding:12px 14px; margin:14px 0; }}
.strategic-next-step-robustness {{ border-left:3px solid #63d39a; background:#10151d; padding:12px 14px; margin:14px 0; }}
.strategic-followup {{ border-left:3px solid #f1c84b; background:#17170f; padding:12px 14px; margin:14px 0; }}
.strategic-followup.terminal {{ border-left-color:#ef7b7b; background:#1c1314; }}
.strategic-next-step-options {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:12px; }}
.strategic-option {{ border:1px solid #374252; background:#171d27; border-radius:10px; padding:14px; }}
.strategic-option h3 {{ color:#f1c84b; margin-bottom:10px; }}
.strategic-option p {{ margin:7px 0; }}
.strategic-next-step-caution {{ margin-top:14px; color:#f0c783; font-size:12px; }}
#strategic-run-next {{ padding:12px 18px; font-size:15px; }}
@media(max-width:800px) {{ .strategic-next-step-options {{ grid-template-columns:1fr; }} }}
@media print {{ .strategic-next-step-overlay,.strategic-next-step-summary .toolbar {{ display:none !important; }} }}
</style>
<div class="card s12 strategic-next-step-summary">
  <h2>Strategic next step</h2>
  <p><strong>{escape(analysis.headline)}</strong></p>
  <p class="subtle">{escape(analysis.observation)}</p>
  <div class="toolbar"><button type="button" id="strategic-next-step-open">Review strategic next-step options</button></div>
</div>
<div id="strategic-next-step-modal" class="strategic-next-step-overlay" hidden role="dialog" aria-modal="true" aria-labelledby="strategic-next-step-title">
  <section class="strategic-next-step-dialog">
    <div class="strategic-next-step-head"><div><div class="eyebrow">SCOUT research analysis</div><h2 id="strategic-next-step-title">Strategic next-step options</h2><p><strong>{escape(analysis.headline)}</strong></p></div><button type="button" id="strategic-next-step-close">Close</button></div>
    <div class="strategic-next-step-observation"><strong>What this run is showing:</strong><br>{escape(analysis.observation)}</div>
    <div class="strategic-next-step-robustness"><strong>Robustness read:</strong><br>{robustness}</div>
    {followup_html}
    <div class="strategic-next-step-options">{options}</div>
    <div class="strategic-next-step-caution">{escape(analysis.caution)}</div>
    <div class="toolbar"><button type="button" id="strategic-next-step-dismiss">Keep researching manually</button></div>
  </section>
</div>
"""


def _render_followup(followup: StrategicFollowupPlan | None) -> str:
    if followup is None:
        return ""
    css_class = "strategic-followup" + (" terminal" if not followup.can_run else "")
    heading = (
        "Iteration decision" if followup.can_run else "SCOUT would stop honing this variable here"
    )
    button = ""
    if followup.can_run:
        assert followup.sweep_variable is not None
        assert followup.from_value is not None
        assert followup.to_value is not None
        assert followup.step_value is not None
        button = (
            '<div class="toolbar">'
            f'<button type="button" id="strategic-run-next" data-sweep-variable="{escape(followup.sweep_variable)}" '
            f'data-sweep-from="{followup.from_value:g}" data-sweep-to="{followup.to_value:g}" '
            f'data-sweep-step="{followup.step_value:g}">{escape(followup.button_label)}</button>'
            '<span class="subtle">This explicit click updates only Section 5 and then starts the next run.</span>'
            "</div>"
        )
    return (
        f'<div class="{css_class}"><strong>{escape(heading)}:</strong><br>'
        f"{escape(followup.message)}{button}</div>"
    )


__all__ = ["render_strategic_next_step_html"]
