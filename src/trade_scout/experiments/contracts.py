"""Typed contracts for reproducible Trade Scout research experiments.

The experiment layer orchestrates research modules and records provenance. It deliberately does not
implement features, patterns, outcomes, risk policies, or statistical inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ResearchMode(StrEnum):
    """Governance mode declared before an experiment is executed."""

    EXPLORATORY = "EXPLORATORY"
    CONFIRMATORY = "CONFIRMATORY"
    PRODUCTION_MONITORING = "PRODUCTION_MONITORING"


class ExperimentStatus(StrEnum):
    """Durable lifecycle state for one experiment run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    """Resolved, immutable analytical request supplied to the experiment runner."""

    name: str
    hypothesis: str
    mode: ResearchMode
    dataset_version: str
    universe_version: str
    code_version: str
    config_schema_version: str
    resolved_configuration: dict[str, JSONValue]
    hypothesis_family_id: str | None = None
    parent_experiment_id: str | None = None
    random_seed: int | None = None

    def __post_init__(self) -> None:
        required = {
            "name": self.name,
            "hypothesis": self.hypothesis,
            "dataset_version": self.dataset_version,
            "universe_version": self.universe_version,
            "code_version": self.code_version,
            "config_schema_version": self.config_schema_version,
        }
        empty = [key for key, value in required.items() if not value.strip()]
        if empty:
            raise ValueError(f"experiment definition has empty required fields: {', '.join(empty)}")


@dataclass(frozen=True, slots=True)
class StageResult:
    """Machine-readable result returned by one orchestrated research stage."""

    stage_name: str
    outputs: dict[str, JSONValue] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.stage_name.strip():
            raise ValueError("stage_name must be non-empty")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("stage warnings must be non-empty")


@dataclass(frozen=True, slots=True)
class ExperimentContext:
    """Read-only context passed to analytical stages during one run."""

    experiment_id: str
    definition: ExperimentDefinition


class ResearchStage(Protocol):
    """Public orchestration boundary implemented by downstream analytical stage adapters."""

    @property
    def name(self) -> str:
        """Return the stable stage name recorded in the experiment manifest."""

    def run(self, context: ExperimentContext) -> StageResult:
        """Execute this stage without mutating the experiment definition."""


@dataclass(frozen=True, slots=True)
class StageRecord:
    """Auditable execution record for one research stage."""

    stage_name: str
    started_at: str
    completed_at: str
    output_checksum: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    """Durable record sufficient to identify and reproduce an experiment run."""

    experiment_id: str
    definition: ExperimentDefinition
    status: ExperimentStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    stages: tuple[StageRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    failure_type: str | None = None
    failure_message: str | None = None
    manifest_checksum: str | None = None
    reproduction_of: str | None = None


class Clock(Protocol):
    """Injectable UTC clock used to make runner behavior testable."""

    def __call__(self) -> datetime: ...


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class IdFactory(Protocol):
    """Injectable immutable experiment-ID factory."""

    def __call__(self) -> str: ...


class ManifestStore(Protocol):
    """Persistence boundary used by the runner and integrity auditor."""

    def write_manifest(self, manifest: ExperimentManifest) -> None: ...

    def write_stage_output(
        self, experiment_id: str, stage_name: str, output: dict[str, JSONValue]
    ) -> str: ...

    def read_manifest(self, experiment_id: str) -> ExperimentManifest: ...

    def read_stage_output(self, experiment_id: str, stage_name: str) -> dict[str, JSONValue]: ...


class ExperimentExecutionError(RuntimeError):
    """Raised after a failed run has been durably recorded."""

    def __init__(self, experiment_id: str, cause: BaseException) -> None:
        super().__init__(f"experiment {experiment_id} failed: {type(cause).__name__}: {cause}")
        self.experiment_id = experiment_id
        self.__cause__ = cause


def ensure_json_value(value: Any) -> JSONValue:
    """Validate that a value can be represented in an immutable experiment manifest."""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [ensure_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("manifest/configuration mapping keys must be strings")
            result[key] = ensure_json_value(item)
        return result
    raise TypeError(f"unsupported manifest/configuration value type: {type(value).__name__}")
