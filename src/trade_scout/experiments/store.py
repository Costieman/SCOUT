"""Local filesystem persistence for experiment manifests and stage artifacts.

This is deliberately a simple Version 1 store. Large analytical outputs may later use Parquet or
DuckDB, but the experiment runner only requires a stable persistence contract.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    JSONValue,
    ResearchMode,
    StageRecord,
)
from trade_scout.experiments.serialization import canonical_json, sha256_json


class FileManifestStore:
    """Persist experiment metadata and small JSON stage outputs beneath one root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write_manifest(self, manifest: ExperimentManifest) -> None:
        """Atomically persist a manifest with a checksum over the checksum-free representation."""

        run_dir = self._run_dir(manifest.experiment_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        checksum_free = replace(manifest, manifest_checksum=None)
        final_manifest = replace(manifest, manifest_checksum=sha256_json(checksum_free))
        path = run_dir / "manifest.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(canonical_json(final_manifest) + "\n", encoding="utf-8")
        temporary.replace(path)

    def write_stage_output(
        self, experiment_id: str, stage_name: str, output: dict[str, JSONValue]
    ) -> str:
        """Persist one small stage output and return its content checksum."""

        safe_name = _safe_stage_name(stage_name)
        run_dir = self._run_dir(experiment_id) / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = canonical_json(output)
        checksum = sha256_json(output)
        path = run_dir / f"{safe_name}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def read_manifest(self, experiment_id: str) -> ExperimentManifest:
        """Load and checksum-verify a previously persisted manifest."""

        path = self._run_dir(experiment_id) / "manifest.json"
        raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        manifest = _manifest_from_dict(raw)
        expected = manifest.manifest_checksum
        if expected is None:
            raise ValueError(f"manifest {experiment_id} has no checksum")
        actual = sha256_json(replace(manifest, manifest_checksum=None))
        if actual != expected:
            raise ValueError(f"manifest checksum mismatch for {experiment_id}")
        return manifest

    def read_stage_output(self, experiment_id: str, stage_name: str) -> dict[str, JSONValue]:
        """Load one persisted stage output without weakening its JSON contract."""

        safe_name = _safe_stage_name(stage_name)
        path = self._run_dir(experiment_id) / "artifacts" / f"{safe_name}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                "stage output must be a JSON mapping: "
                f"experiment={experiment_id}, stage={stage_name}"
            )
        result: dict[str, JSONValue] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ValueError("stage output mapping keys must be strings")
            result[key] = cast(JSONValue, value)
        return result

    def _run_dir(self, experiment_id: str) -> Path:
        if not experiment_id or any(character in experiment_id for character in "/\\"):
            raise ValueError("experiment_id must be a non-empty path-safe identifier")
        return self._root / experiment_id


def _safe_stage_name(stage_name: str) -> str:
    if not stage_name or any(character in stage_name for character in "/\\"):
        raise ValueError("stage_name must be a non-empty path-safe identifier")
    return stage_name.replace(" ", "_")


def _manifest_from_dict(raw: dict[str, object]) -> ExperimentManifest:
    definition_raw = cast(dict[str, object], raw["definition"])
    definition = ExperimentDefinition(
        name=str(definition_raw["name"]),
        hypothesis=str(definition_raw["hypothesis"]),
        mode=ResearchMode(str(definition_raw["mode"])),
        dataset_version=str(definition_raw["dataset_version"]),
        universe_version=str(definition_raw["universe_version"]),
        code_version=str(definition_raw["code_version"]),
        config_schema_version=str(definition_raw["config_schema_version"]),
        resolved_configuration=cast(dict[str, JSONValue], definition_raw["resolved_configuration"]),
        hypothesis_family_id=_optional_string(definition_raw.get("hypothesis_family_id")),
        parent_experiment_id=_optional_string(definition_raw.get("parent_experiment_id")),
        random_seed=cast(int | None, definition_raw.get("random_seed")),
    )
    stage_records = tuple(
        StageRecord(
            stage_name=str(item["stage_name"]),
            started_at=str(item["started_at"]),
            completed_at=str(item["completed_at"]),
            output_checksum=str(item["output_checksum"]),
            warnings=tuple(str(warning) for warning in cast(list[object], item["warnings"])),
        )
        for item in cast(list[dict[str, object]], raw.get("stages", []))
    )
    return ExperimentManifest(
        experiment_id=str(raw["experiment_id"]),
        definition=definition,
        status=ExperimentStatus(str(raw["status"])),
        created_at=str(raw["created_at"]),
        started_at=_optional_string(raw.get("started_at")),
        completed_at=_optional_string(raw.get("completed_at")),
        stages=stage_records,
        warnings=tuple(str(item) for item in cast(list[object], raw.get("warnings", []))),
        failure_type=_optional_string(raw.get("failure_type")),
        failure_message=_optional_string(raw.get("failure_message")),
        manifest_checksum=_optional_string(raw.get("manifest_checksum")),
        reproduction_of=_optional_string(raw.get("reproduction_of")),
    )


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
