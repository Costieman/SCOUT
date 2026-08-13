"""Out-of-sample, walk-forward, robustness, and research-promotion validation."""

from trade_scout.validation.completeness import (
    EvidenceAssignment,
    EvidenceTargetKind,
    IncompleteValidationEvidenceError,
    ValidationCompleteness,
    assess_validation_completeness,
)
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
from trade_scout.validation.execution import (
    GovernedValidationWorkflow,
    ValidationExecutionContext,
    ValidationExecutionError,
    ValidationExecutionReceipt,
    ValidationTarget,
    ValidationTargetExecutor,
    ValidationTargetResult,
    ValidationTargetType,
    execute_validation_design,
    materialize_validation_targets,
)
from trade_scout.validation.experiment_workflow import (
    ExperimentRunnerGovernedValidationWorkflow,
    ExperimentRunnerValidationReceipt,
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
from trade_scout.validation.plan_store import (
    FileRobustnessPlanStore,
    FileValidationPlanStore,
    FrozenValidationPlanStoreError,
)
from trade_scout.validation.reporting import (
    MultiplicitySummary,
    ValidationReviewBundle,
    ValidationReviewSummary,
    ValidationRoleCount,
    assemble_validation_review_bundle,
    summarize_validation_review,
)
from trade_scout.validation.robustness import (
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
    consolidation_breakout_robustness_plan,
)
from trade_scout.validation.runner_adapter import (
    ExperimentRunnerValidationTargetExecutor,
    ValidationEvidenceExtractor,
    ValidationExperimentArtifactReader,
    ValidationTargetExperimentExecution,
    ValidationTargetExperimentFactory,
    ValidationTargetExperimentSpec,
)
from trade_scout.validation.store import FileValidationReviewStore, ValidationReviewStoreError
from trade_scout.validation.time_ordered import build_fixed_holdout_plan, build_walk_forward_plan

__all__ = [
    "AdjustedPValue",
    "ComparatorDefinition",
    "ComparatorKind",
    "ConfidenceInterval",
    "DateInterval",
    "EffectEstimate",
    "EvidenceAssignment",
    "EvidenceRole",
    "EvidenceSnapshot",
    "EvidenceTargetKind",
    "ExperimentRunnerGovernedValidationWorkflow",
    "ExperimentRunnerValidationReceipt",
    "ExperimentRunnerValidationTargetExecutor",
    "FileRobustnessPlanStore",
    "FileValidationPlanStore",
    "FileValidationReviewStore",
    "FrozenValidationPlanStoreError",
    "GovernedValidationWorkflow",
    "HypothesisFamily",
    "IncompleteValidationEvidenceError",
    "MetricEstimate",
    "MultiplicityMethod",
    "MultiplicitySummary",
    "ParameterAxis",
    "ParameterCell",
    "ParameterSurface",
    "RobustnessChallenge",
    "RobustnessKind",
    "RobustnessPlan",
    "SampleAccounting",
    "ValidationCompleteness",
    "ValidationEvidenceExtractor",
    "ValidationEvidenceReport",
    "ValidationExecutionContext",
    "ValidationExecutionError",
    "ValidationExecutionReceipt",
    "ValidationExperimentArtifactReader",
    "ValidationPlan",
    "ValidationReviewBundle",
    "ValidationReviewStoreError",
    "ValidationReviewSummary",
    "ValidationRole",
    "ValidationRoleCount",
    "ValidationSegment",
    "ValidationTarget",
    "ValidationTargetExecutor",
    "ValidationTargetExperimentExecution",
    "ValidationTargetExperimentFactory",
    "ValidationTargetExperimentSpec",
    "ValidationTargetResult",
    "ValidationTargetType",
    "WalkForwardFold",
    "adjust_p_values",
    "assemble_validation_review_bundle",
    "assess_validation_completeness",
    "build_fixed_holdout_plan",
    "build_parameter_surface",
    "build_walk_forward_plan",
    "consolidation_breakout_robustness_plan",
    "execute_validation_design",
    "materialize_validation_targets",
    "summarize_validation_review",
]
