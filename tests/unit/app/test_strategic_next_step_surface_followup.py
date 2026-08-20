from dataclasses import dataclass

from trade_scout.app.strategic_followup import StrategicFollowupPlan
from trade_scout.app.strategic_next_step_surface import render_strategic_next_step_html


@dataclass(frozen=True)
class _Option:
    title: str = "Resolve neighborhood"
    direction: str = "Narrow locally"
    proposed_range: str = "10 to 20"
    rationale: str = "Interior region"
    falsifier: str = "Neighbors fail"


@dataclass(frozen=True)
class _Analysis:
    headline: str = "Test"
    observation: str = "Observed"
    robustness: str = "Robust"
    caution: str = "Exploratory"
    options: tuple[_Option, ...] = (_Option(),)


def test_actionable_followup_renders_machine_values() -> None:
    html = render_strategic_next_step_html(
        _Analysis(),
        StrategicFollowupPlan(
            status="run_next",
            message="Continue",
            sweep_variable="target_fixed",
            from_value=10,
            to_value=20,
            step_value=2.5,
        ),
    )
    assert 'id="strategic-run-next"' in html
    assert 'data-sweep-variable="target_fixed"' in html
    assert 'data-sweep-step="2.5"' in html


def test_terminal_followup_has_no_run_button() -> None:
    html = render_strategic_next_step_html(
        _Analysis(),
        StrategicFollowupPlan(status="control_dominated_flat", message="Switch variable"),
    )
    assert "SCOUT would stop honing this variable here" in html
    assert 'id="strategic-run-next"' not in html
