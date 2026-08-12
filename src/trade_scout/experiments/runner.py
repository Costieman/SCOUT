"""Orchestration-only experiment runner for Trade Scout research.

The runner owns lifecycle, persistence, provenance and failure visibility. Analytical meaning remains
inside the registered research stages supplied to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from trade_scout.experiments.contracts import (
    Clock,
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentManifest,
    ExperimentStatus,
    IdFactory,
    ManifestStore,
    ResearchStage,
    StageRecord,
    utc_now,
)


class ExperimentRunner:
    """Execute ordered research stages while durably recording the complete run lifecycle."""

    def __init__(
        self,
        store: ManifestStore,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._id_factory = id_factory or _default_id

    def run(
        self,
        definition: ExperimentDefinition,
        stages: Iterable[ResearchStage],
        *,
        reproduction_of: str | None = None,
    ) -> ExperimentManifest:
        """Run all stages in order and return the verified terminal manifest.

        A failed stage produces and persists a FAILED manifest before ExperimentExecutionError is
        raised. This intentionally favors visible failure over partial plausible-looking output.
        """

        ordered_stages = tuple(stages)
        _validate_stage_sequence(ordered_stages)
        experiment_id = self._id_factory()
        created = _timestamp(self._clock())
        manifest = ExperimentManifest(
            experiment_id=experiment_id,
            definition=definition,
            status=ExperimentStatus.PENDING,
            created_at=created,
            reproduction_of=reproduction_of,
        )
        self._store.write_manifest(manifest)

        manifest = replace(
            manifest,
            status=ExperimentStatus.RUNNING,
            started_at=_timestamp(self._clock()),
        )
        self._store.write_manifest(manifest)

        context = ExperimentContext(experiment_id=experiment_id, definition=definition)
        stage_records: list[StageRecord] = []
        warnings: list[str] = []

        try:
            for stage in ordered_stages:
                started_at = _timestamp(self._clock())
                result = stage.run(context)
                if result.stage_name != stage.name:
                    raise ValueError(
                        f"stage {stage.name!r} returned mismatched result name {result.stage_name!r}"
                    )
                checksum = self._store.write_stage_output(
                    experiment_id, result.stage_name, result.outputs
                )
                completed_at = _timestamp(self._clock())
                stage_records.append(
                    StageRecord(
                        stage_name=result.stage_name,
                        started_at=started_at,
                        completed_at=completed_at,
                        output_checksum=checksum,
                        warnings=result.warnings,
                    )
                )
                warnings.extend(result.warnings)
                manifest = replace(
                    manifest,
                    stages=tuple(stage_records),
                    warnings=tuple(warnings),
                )
                self._store.write_manifest(manifest)
        except Exception as cause:
            failed = replace(
                manifest,
                status=ExperimentStatus.FAILED,
                completed_at=_timestamp(self._clock()),
                stages=tuple(stage_records),
                warnings=tuple(warnings),
                failure_type=type(cause).__name__,
                failure_message=str(cause),
            )
            self._store.write_manifest(failed)
            raise ExperimentExecutionError(experiment_id, cause) from cause

        succeeded = replace(
            manifest,
            status=ExperimentStatus.SUCCEEDED,
            completed_at=_timestamp(self._clock()),
            stages=tuple(stage_records),
            warnings=tuple(warnings),
        )
        self._store.write_manifest(succeeded)
        return self._store.read_manifest(experiment_id)

    def reproduce(
        self,
        experiment_id: str,
        stages: Iterable[ResearchStage],
    ) -> ExperimentManifest:
        """Execute a new run from an existing immutable manifest definition."""

        source = self._store.read_manifest(experiment_id)
        if source.status is not ExperimentStatus.SUCCEEDED:
            raise ValueError("only successful experiments may be reproduced")
        return self.run(source.definition, stages, reproduction_of=source.experiment_id)


def _default_id() -> str:
    return f"exp_{uuid4().hex}"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("experiment runner clock must return timezone-aware timestamps")
    return value.isoformat()


def _validate_stage_sequence(stages: tuple[ResearchStage, ...]) -> None:
    names = [stage.name for stage in stages]
    if any(not name.strip() for name in names):
        raise ValueError("research stage names must be non-empty")
    if len(names) != len(set(names)):
        raise ValueError("research stage names must be unique within one experiment")
