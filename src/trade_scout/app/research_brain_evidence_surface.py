# ruff: noqa: E501
"""Presentation-only governed-evidence coverage panel for Research Brains."""

from __future__ import annotations

from html import escape

from trade_scout.app.research_brain_evidence import (
    BrainEvidenceCoverageState,
    BrainExperimentEvidenceCoverage,
)
from trade_scout.app.research_brain_service import ResearchBrainView

_INSERT_MARKER = "<details><summary>Advanced: focus boundaries</summary>"


def attach_research_brain_evidence_html(html: str, view: ResearchBrainView | None) -> str:
    """Attach governed validation coverage without replacing the descriptive Brain Review."""

    if view is None:
        return html
    if _INSERT_MARKER not in html:
        raise RuntimeError("Research Brain HTML omitted the evidence insertion marker")
    return html.replace(_INSERT_MARKER, _render_evidence(view) + _INSERT_MARKER, 1)


def _render_evidence(view: ResearchBrainView) -> str:
    summary = view.evidence_summary
    rows = "".join(_row(item) for item in summary.experiments)
    if not rows:
        rows = '<tr><td colspan="6" class="subtle">No attached experiments are available for governed evidence review.</td></tr>'
    store_warning = ""
    if summary.store_integrity_errors:
        details = "".join(f"<li>{escape(item)}</li>" for item in summary.store_integrity_errors)
        store_warning = (
            '<div class="error"><strong>Validation-review integrity warning:</strong> '
            "one or more stored reviews could not be verified. They were not counted below."
            f"<ul>{details}</ul></div>"
        )
    return f"""<div class="review" id="brain-governed-evidence">
<h3>Evidence coverage — what has actually been challenged?</h3>
<div class="banner"><strong>This is coverage, not a grade.</strong> {escape(summary.interpretation_boundary)}</div>
<div class="review-columns">
<div class="review-box"><strong>Governed review</strong><div style="font-size:24px;font-weight:800">{summary.reviewed_experiment_count}</div><span class="subtle">attached experiments with a checksum-verified validation review</span></div>
<div class="review-box"><strong>Time-ordered</strong><div style="font-size:24px;font-weight:800">{summary.walk_forward_experiment_count}</div><span class="subtle">attached experiments with walk-forward evidence</span></div>
<div class="review-box"><strong>Final holdout</strong><div style="font-size:24px;font-weight:800">{summary.final_holdout_experiment_count}</div><span class="subtle">attached experiments with final-holdout evidence</span></div>
</div>
<div class="section-note" style="margin-top:12px;border-left-color:#f1c84b"><strong>Best next challenge:</strong> {escape(summary.next_challenge)}</div>
{store_warning}
<div class="scroll" style="margin-top:12px"><table><thead><tr><th>Experiment</th><th>Coverage</th><th>Comparator</th><th>Uncertainty</th><th>Robustness</th><th>Search correction</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="subtle" style="margin-top:8px">The descriptive Brain Review above can summarize historical results. This panel is stricter: it only reports governed validation artifacts already persisted by SCOUT's validation system.</div>
</div>"""


def _row(item: BrainExperimentEvidenceCoverage) -> str:
    comparator = (
        ", ".join(_comparator_label(kind.value) for kind in item.comparator_kinds)
        if item.comparator_kinds
        else "Not in governed review"
    )
    robustness = "Present" if item.has_robustness_evidence else "Not present"
    uncertainty = "Present" if item.has_uncertainty_intervals else "Not present"
    multiplicity = "Present" if item.has_multiplicity_metadata else "Not present"
    reports = (
        '<span class="plain-state">Review: '
        + ", ".join(escape(report_id) for report_id in item.report_ids)
        + "</span>"
        if item.report_ids
        else ""
    )
    return (
        "<tr>"
        f'<td><a href="/research/experiments?experiment={escape(item.experiment_id)}"><code>{escape(item.experiment_id)}</code></a></td>'
        f"<td>{_coverage_label(item.coverage_state)}{reports}</td>"
        f"<td>{escape(comparator)}</td>"
        f"<td>{uncertainty}</td>"
        f"<td>{robustness}</td>"
        f"<td>{multiplicity}</td>"
        "</tr>"
    )


def _coverage_label(state: BrainEvidenceCoverageState) -> str:
    labels = {
        BrainEvidenceCoverageState.EXPLORATORY_ONLY: "Exploratory history only",
        BrainEvidenceCoverageState.VALIDATION_REVIEW_PRESENT: "Governed validation review present",
        BrainEvidenceCoverageState.TIME_ORDERED_EVIDENCE_PRESENT: "Time-ordered evidence present",
        BrainEvidenceCoverageState.FINAL_HOLDOUT_PRESENT: "Final holdout evidence present",
    }
    return escape(labels[state])


def _comparator_label(value: str) -> str:
    labels = {
        "UNCONDITIONAL": "Unconditional baseline",
        "TREND_MATCHED": "Trend-matched",
        "REGIME_MATCHED": "Regime-matched",
        "SECTOR_MATCHED": "Sector-matched",
        "RANDOMIZED_PSEUDO_EVENT": "Randomized timing",
        "SIMPLE_EVENT_BASELINE": "Simple event baseline",
    }
    return labels.get(value, value.replace("_", " ").title())


__all__ = ["attach_research_brain_evidence_html"]
