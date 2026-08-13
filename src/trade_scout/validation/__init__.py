"""Out-of-sample, walk-forward, robustness, and research-promotion validation."""

from trade_scout.validation.contracts import (
    DateInterval,
    SampleAccounting,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)
from trade_scout.validation.robustness import (
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
    consolidation_breakout_robustness_plan,
)
from trade_scout.validation.time_ordered import build_fixed_holdout_plan, build_walk_forward_plan

__all__ = [
    "DateInterval",
    "RobustnessChallenge",
    "RobustnessKind",
    "RobustnessPlan",
    "SampleAccounting",
    "ValidationPlan",
    "ValidationRole",
    "ValidationSegment",
    "WalkForwardFold",
    "build_fixed_holdout_plan",
    "build_walk_forward_plan",
    "consolidation_breakout_robustness_plan",
]
