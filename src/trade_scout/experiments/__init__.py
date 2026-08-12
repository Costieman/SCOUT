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
    "ExperimentRunner",
    "ExperimentStatus",
    "FileBatchPlanStore",
    "FileManifestStore",
    "FirstProgramExperiment",
    "FirstProgramGrid",
    "IndexedManifestStore",
    "PlannedExperiment",
    "ProgramStep",
    "ResearchMode",
    "ResearchStage",
    "StageFactory",
    "StageResult",
    "expand_grid",
    "first_program_step",
    "plan_experiment_batch",
    "validate_first_research_program",
    "validate_plan_unchanged",
]
