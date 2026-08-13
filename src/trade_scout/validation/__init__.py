"""Out-of-sample, walk-forward, robustness, and research-promotion validation."""

from trade_scout.validation.contracts import (
    DateInterval,
    SampleAccounting,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)
from trade_scout.validation.evidence import (
    ComparatorDefinition,
    ComparatorKind,
    ConfidenceInterval,
    EffectEstimate,
    EvidenceRole,
    EvidenceSnapshot,
    MetricEstimate,
    ValidationEvidenceReport,
)
from trade_scout.validation.multiplicity import (
    AdjustedPValue,
    HypothesisFamily,
    MultiplicityMethod,
    adjust_p_values,
)
from trade_scout.validation.parameter_surface import (
    ParameterAxis,
    ParameterCell,
    ParameterSurface,
    build_parameter_surface,
)
from trade_scout.validation.robustness import (
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
    consolidation_breakout_robustness_plan,
)
from trade_scout.validation.time_ordered import build_fixed_holdout_plan, build_walk_forward_plan

__all__ = [
    "AdjustedPValue",
    "ComparatorDefinition",
    "ComparatorKind",
    "ConfidenceInterval",
    "DateInterval",
    "EffectEstimate",
    "EvidenceRole",
    "EvidenceSnapshot",
    "HypothesisFamily",
    "MetricEstimate",
    "MultiplicityMethod",
    "ParameterAxis",
    "ParameterCell",
    "ParameterSurface",
    "RobustnessChallenge",
    "RobustnessKind",
    "RobustnessPlan",
    "SampleAccounting",
    "ValidationEvidenceReport",
    "ValidationPlan",
    "ValidationRole",
    "ValidationSegment",
    "WalkForwardFold",
    "adjust_p_values",
    "build_fixed_holdout_plan",
    "build_parameter_surface",
    "build_walk_forward_plan",
    "consolidation_breakout_robustness_plan",
]
