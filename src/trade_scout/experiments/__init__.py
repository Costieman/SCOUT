"""Trade Scout experiment orchestration and reproducibility interfaces."""

from trade_scout.experiments.batch import (
    BatchExecutionSummary,
    BatchFailurePolicy,
    BatchRunRecord,
    ExperimentBatchExecutor,
    StageFactory,
)
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
    ResearchStage,
    StageResult,
)
from trade_scout.experiments.decision_ledger import FileResearchDecisionLedger
from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    validate_decision_supersession,
)
from trade_scout.experiments.first_research_program import (
    FIRST_RESEARCH_PROGRAM,
    FirstProgramExperiment,
    FirstProgramGrid,
    ProgramStep,
    first_program_step,
    validate_first_research_program,
)
from trade_scout.experiments.plan_store import FileBatchPlanStore
from trade_scout.experiments.planner import (
    ExperimentBatchPlan,
    ExperimentPlanningError,
    PlannedExperiment,
    plan_experiment_batch,
    validate_plan_unchanged,
)
from trade_scout.experiments.program_progress import (
    ExperimentRegistryReader,
    FirstResearchProgramProgress,
    ProgramAssignment,
    ProgramProgressionError,
    ProgramStepProgress,
    ProgramStepState,
    evaluate_first_research_program_progress,
)
from trade_scout.experiments.registry import (
    DuckDBExperimentRegistry,
    ExperimentIndexRecord,
    IndexedManifestStore,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.sweeps import expand_grid

__all__ = [
    "FIRST_RESEARCH_PROGRAM",
    "BatchExecutionSummary",
    "BatchFailurePolicy",
    "BatchRunRecord",
    "DuckDBExperimentRegistry",
    "ExperimentBatchExecutor",
    "ExperimentBatchPlan",
    "ExperimentContext",
    "ExperimentDefinition",
    "ExperimentExecutionError",
    "ExperimentIndexRecord",
    "ExperimentManifest",
    "ExperimentPlanningError",
    "ExperimentRegistryReader",
    "ExperimentRunner",
    "ExperimentStatus",
    "FileBatchPlanStore",
    "FileManifestStore",
    "FileResearchDecisionLedger",
    "FirstProgramExperiment",
    "FirstProgramGrid",
    "FirstResearchProgramProgress",
    "IndexedManifestStore",
    "PlannedExperiment",
    "ProductionEligibilityAttestation",
    "ProgramAssignment",
    "ProgramProgressionError",
    "ProgramStep",
    "ProgramStepProgress",
    "ProgramStepState",
    "ResearchDecision",
    "ResearchDecisionError",
    "ResearchDecisionState",
    "ResearchMode",
    "ResearchStage",
    "StageFactory",
    "StageResult",
    "evaluate_first_research_program_progress",
    "expand_grid",
    "first_program_step",
    "plan_experiment_batch",
    "validate_decision_supersession",
    "validate_first_research_program",
    "validate_plan_unchanged",
]
