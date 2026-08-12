"""Integrity auditing for persisted experiment manifests and stage outputs.

An experiment is reproducible only if the manifest can still be verified and every recorded stage
artifact still matches the checksum captured at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.experiments.contracts import ManifestStore
from trade_scout.experiments.serialization import sha256_json


class StageIntegrityState(StrEnum):
    """Integrity state of one stage output referenced by an experiment manifest."""

    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    UNREADABLE = "UNREADABLE"


@dataclass(frozen=True, slots=True)
class StageIntegrityRecord:
    """Checksum audit result for one persisted stage output."""

    stage_name: str
    state: StageIntegrityState
    expected_checksum: str
    actual_checksum: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ExperimentIntegrityReport:
    """Complete integrity assessment for one persisted experiment run."""

    experiment_id: str
    manifest_verified: bool
    manifest_detail: str
    stages: tuple[StageIntegrityRecord, ...]

    @property
    def verified(self) -> bool:
        """Return true only when manifest and every referenced stage artifact verify."""

        return self.manifest_verified and all(
            stage.state is StageIntegrityState.VERIFIED for stage in self.stages
        )

    def require_verified(self) -> None:
        """Raise before reproduction/inspection if persisted evidence no longer verifies."""

        if self.verified:
            return
        failures = ", ".join(
            f"{stage.stage_name}:{stage.state.value}"
            for stage in self.stages
            if stage.state is not StageIntegrityState.VERIFIED
        )
        detail = self.manifest_detail
        if failures:
            detail = f"{detail}; stage failures={failures}"
        raise ExperimentIntegrityError(
            f"experiment integrity verification failed for {self.experiment_id}: {detail}"
        )


class ExperimentIntegrityError(RuntimeError):
    """Raised when an experiment's persisted reproducibility record is not intact."""


def audit_experiment(store: ManifestStore, experiment_id: str) -> ExperimentIntegrityReport:
    """Verify the authoritative manifest and all stage-output checksums it references."""

    try:
        manifest = store.read_manifest(experiment_id)
    except Exception as error:
        return ExperimentIntegrityReport(
            experiment_id=experiment_id,
            manifest_verified=False,
            manifest_detail=f"{type(error).__name__}: {error}",
            stages=(),
        )

    records: list[StageIntegrityRecord] = []
    for stage in manifest.stages:
        try:
            output = store.read_stage_output(experiment_id, stage.stage_name)
        except FileNotFoundError as error:
            records.append(
                StageIntegrityRecord(
                    stage_name=stage.stage_name,
                    state=StageIntegrityState.MISSING,
                    expected_checksum=stage.output_checksum,
                    actual_checksum=None,
                    detail=f"{type(error).__name__}: {error}",
                )
            )
            continue
        except Exception as error:
            records.append(
                StageIntegrityRecord(
                    stage_name=stage.stage_name,
                    state=StageIntegrityState.UNREADABLE,
                    expected_checksum=stage.output_checksum,
                    actual_checksum=None,
                    detail=f"{type(error).__name__}: {error}",
                )
            )
            continue

        actual = sha256_json(output)
        if actual == stage.output_checksum:
            state = StageIntegrityState.VERIFIED
            detail = "stage output checksum matches manifest"
        else:
            state = StageIntegrityState.CHECKSUM_MISMATCH
            detail = "stage output checksum does not match manifest"
        records.append(
            StageIntegrityRecord(
                stage_name=stage.stage_name,
                state=state,
                expected_checksum=stage.output_checksum,
                actual_checksum=actual,
                detail=detail,
            )
        )

    return ExperimentIntegrityReport(
        experiment_id=experiment_id,
        manifest_verified=True,
        manifest_detail="manifest checksum verified",
        stages=tuple(records),
    )
