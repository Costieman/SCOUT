"""Shared progress and failure contract for long-running SCOUT operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic


class OperationState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class OperationFailure:
    """Machine-readable failure localised to one operation unit and stage."""

    code: str
    message: str
    stage: str
    asset_or_parameter: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("failure code must be non-empty")
        if not self.message.strip():
            raise ValueError("failure message must be non-empty")
        if not self.stage.strip():
            raise ValueError("failure stage must be non-empty")


@dataclass(frozen=True, slots=True)
class OperationProgressEvent:
    """Vendor-neutral progress snapshot shared by imports and research jobs."""

    operation_id: str
    operation_type: str
    stage: str
    state: OperationState
    completed: int
    total: int | None
    elapsed_seconds: float
    asset_or_parameter: str | None = None
    throughput_per_second: float | None = None
    retry_count: int = 0
    wait_seconds: float = 0.0
    failure: OperationFailure | None = None
    contract_version: str = "operation-progress-v1"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("operation_id", self.operation_id),
            ("operation_type", self.operation_type),
            ("stage", self.stage),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.completed < 0:
            raise ValueError("completed cannot be negative")
        if self.total is not None and self.total < 0:
            raise ValueError("total cannot be negative")
        if self.total is not None and self.completed > self.total:
            raise ValueError("completed cannot exceed total")
        if self.elapsed_seconds < 0 or self.wait_seconds < 0:
            raise ValueError("durations cannot be negative")
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative")
        if self.throughput_per_second is not None and self.throughput_per_second < 0:
            raise ValueError("throughput_per_second cannot be negative")
        if self.state is OperationState.FAILED and self.failure is None:
            raise ValueError("FAILED progress events require failure metadata")
        if self.failure is not None and self.failure.stage != self.stage:
            raise ValueError("failure stage must match progress stage")


class OperationProgressTracker:
    """Small monotonic helper for consistent progress snapshots."""

    def __init__(self, operation_id: str, operation_type: str, *, total: int | None = None) -> None:
        if not operation_id.strip() or not operation_type.strip():
            raise ValueError("operation identity must be non-empty")
        if total is not None and total < 0:
            raise ValueError("total cannot be negative")
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.total = total
        self.started = monotonic()

    def event(
        self,
        *,
        stage: str,
        state: OperationState,
        completed: int,
        asset_or_parameter: str | None = None,
        retry_count: int = 0,
        wait_seconds: float = 0.0,
        failure: OperationFailure | None = None,
    ) -> OperationProgressEvent:
        elapsed = monotonic() - self.started
        active_seconds = max(0.0, elapsed - wait_seconds)
        throughput = completed / active_seconds if completed and active_seconds > 0 else None
        return OperationProgressEvent(
            operation_id=self.operation_id,
            operation_type=self.operation_type,
            stage=stage,
            state=state,
            completed=completed,
            total=self.total,
            elapsed_seconds=elapsed,
            asset_or_parameter=asset_or_parameter,
            throughput_per_second=throughput,
            retry_count=retry_count,
            wait_seconds=wait_seconds,
            failure=failure,
        )


__all__ = [
    "OperationFailure",
    "OperationProgressEvent",
    "OperationProgressTracker",
    "OperationState",
]
