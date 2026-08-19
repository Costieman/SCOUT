from types import MappingProxyType

from trade_scout.app.strategy_suite_contract import (
    ThresholdContract,
    threshold_contract,
    validate_all_ready_suites,
    validate_suite_launch_plan,
    value_matches_threshold_contract,
)
from trade_scout.app.strategy_suite_workflow import SuiteLaunchPlan, SuiteLaunchStatus


def test_all_builtin_ready_suite_launches_satisfy_builder_contract() -> None:
    assert validate_all_ready_suites() == ()


def test_static_catalog_precision_accepts_return_20_default() -> None:
    contract = threshold_contract("return_20")
    assert contract == ThresholdContract(-1.0, 10.0, 0.01)
    assert value_matches_threshold_contract(0.05, contract)


def test_invalid_ready_suite_names_exact_threshold_failure() -> None:
    plan = SuiteLaunchPlan(
        suite_id="TEST-BAD-THRESHOLD",
        suite_version="0.1.0",
        launch_status=SuiteLaunchStatus.READY,
        builder_parameters=MappingProxyType(
            {
                "universe": "reviewed_canonical",
                "entry_family": "feature_expression",
                "lookback_years": "2",
                "horizon": "20",
                "expression": "return_20 > 10.005",
                "rank_feature": "return_20",
                "rank_direction": "desc",
                "per_session_limit": "25",
            }
        ),
    )

    issues = validate_suite_launch_plan(plan)

    assert len(issues) == 1
    assert issues[0].field == "entry_condition_1"
    assert issues[0].issue_code == "invalid_threshold"
    assert "return_20 value 10.005" in issues[0].message
    assert "step 0.01" in issues[0].message


def test_non_ready_suite_is_not_misrepresented_as_contract_validated() -> None:
    plan = SuiteLaunchPlan(
        suite_id="TEST-PARTIAL",
        suite_version="0.1.0",
        launch_status=SuiteLaunchStatus.PARTIAL,
        builder_parameters=MappingProxyType({"universe": "reviewed_canonical"}),
        unresolved_capabilities=("missing_detector",),
        note="Not executable yet.",
    )
    assert validate_suite_launch_plan(plan) == ()
