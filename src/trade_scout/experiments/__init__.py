"""Trade Scout experiment orchestration and reproducibility interfaces."""

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
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.sweeps import expand_grid

__all__ = [
    "FIRST_RESEARCH_PROGRAM",
    "ExperimentContext",
    "ExperimentDefinition",
    "ExperimentExecutionError",
    "ExperimentManifest",
    "ExperimentRunner",
    "ExperimentStatus",
    "FileManifestStore",
    "FirstProgramExperiment",
    "FirstProgramGrid",
    "ProgramStep",
    "ResearchMode",
    "ResearchStage",
    "StageResult",
    "expand_grid",
    "first_program_step",
    "validate_first_research_program",
]
