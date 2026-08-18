from __future__ import annotations

from trade_scout.app.strategy_suite_workflow import (
    SuiteLaunchStatus,
    built_in_suite_launch_plans,
    configuration_from_launch_plan,
    is_exact_rerun,
    propose_single_axis_iteration,
    strategy_suite_launch_plan,
)


def test_complete_catalog_has_truthful_launch_status() -> None:
    plans = built_in_suite_launch_plans()

    assert len(plans) == 20
    assert len({plan.suite_id for plan in plans}) == 20
    assert any(plan.launch_status is SuiteLaunchStatus.READY for plan in plans)
    assert any(plan.launch_status is SuiteLaunchStatus.PARTIAL for plan in plans)
    assert any(plan.launch_status is SuiteLaunchStatus.BLOCKED for plan in plans)


def test_structural_pattern_suite_is_blocked_without_approximation() -> None:
    plan = strategy_suite_launch_plan("TS-S08-VCP")

    assert plan.launch_status is SuiteLaunchStatus.BLOCKED
    assert not plan.executable
    assert "structural pattern detector" in plan.note
    assert "sequential_contraction_geometry" in plan.unresolved_capabilities


def test_ready_suite_resolves_to_reproducible_builder_parameters() -> None:
    plan = strategy_suite_launch_plan("TS-S01-CONSOLIDATION-BREAKOUT")

    assert plan.executable
    assert plan.builder_parameters["entry_family"] == "consolidation_breakout"
    assert plan.builder_parameters["duration"] == "30"
    assert plan.query_parameters(brain_id="brain-1")["brain"] == "brain-1"
    assert plan.query_parameters()["suite"] == plan.suite_id


def test_configuration_fingerprint_is_order_independent_and_detects_exact_reruns() -> None:
    plan = strategy_suite_launch_plan("TS-S01-CONSOLIDATION-BREAKOUT")
    first = configuration_from_launch_plan(
        plan,
        overrides={"horizon": "40", "lookback_years": "5"},
    )
    second = configuration_from_launch_plan(
        plan,
        overrides={"lookback_years": "5", "horizon": "40"},
    )

    assert first.fingerprint == second.fingerprint
    assert is_exact_rerun(first, second)
    assert is_exact_rerun(first, second.fingerprint)


def test_one_axis_iteration_changes_only_declared_machine_parameter() -> None:
    plan = strategy_suite_launch_plan("TS-S01-CONSOLIDATION-BREAKOUT")
    current = configuration_from_launch_plan(plan)

    proposal = propose_single_axis_iteration(
        current,
        axis="base_duration",
        proposed_value="40",
    )

    assert proposal.axis == "base_duration"
    assert proposal.prior_value == "30"
    assert proposal.proposed_value == "40"
    assert proposal.configuration.parameters["duration"] == "40"
    assert proposal.configuration.parameters["max_range_pct"] == current.parameters["max_range_pct"]
    assert not is_exact_rerun(proposal.configuration, current)


def test_iteration_rejects_undeclared_or_unresolved_axes() -> None:
    plan = strategy_suite_launch_plan("TS-S01-CONSOLIDATION-BREAKOUT")
    current = configuration_from_launch_plan(plan)

    try:
        propose_single_axis_iteration(current, axis="not_an_axis", proposed_value="x")
    except ValueError as exc:
        assert "not declared" in str(exc)
    else:
        raise AssertionError("undeclared axis must fail closed")

    try:
        propose_single_axis_iteration(current, axis="breakout_margin", proposed_value="1")
    except ValueError as exc:
        assert "not yet machine-resolved" in str(exc)
    else:
        raise AssertionError("unresolved declared axis must fail closed")


def test_partial_suite_cannot_be_promoted_to_configuration() -> None:
    plan = strategy_suite_launch_plan("TS-S04-BB-SQUEEZE")

    assert plan.launch_status is SuiteLaunchStatus.PARTIAL
    try:
        configuration_from_launch_plan(plan)
    except ValueError as exc:
        assert "does not yet have a complete executable bridge" in str(exc)
    else:
        raise AssertionError("partial launch plan must not execute")
