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
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.sweeps import expand_grid

__all__ = [
    "ExperimentContext",
    "ExperimentDefinition",
    "ExperimentExecutionError",
    "ExperimentManifest",
    "ExperimentRunner",
    "ExperimentStatus",
    "FileManifestStore",
    "ResearchMode",
    "ResearchStage",
    "StageResult",
    "expand_grid",
]
