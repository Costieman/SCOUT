"""DuckDB-backed experiment registry for queryable research lineage.

The registry is an index of experiment manifests, not the source of analytical truth. Immutable
manifests and their artifact checksums remain the reproducibility record; the registry provides a
small query surface for experiment discovery, lineage, and status inspection.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterator, Protocol

import duckdb

from trade_scout.experiments.contracts import (
    ExperimentManifest,
    ExperimentStatus,
    JSONValue,
    ManifestStore,
    ResearchMode,
)

_REGISTRY_LOCKS: dict[str, RLock] = {}
_REGISTRY_LOCKS_GUARD = RLock()


class ExperimentRegistry(Protocol):
    """Indexing boundary used to keep registry concerns outside the experiment runner."""

    def register(self, manifest: ExperimentManifest) -> None: ...


@dataclass(frozen=True, slots=True)
class ExperimentIndexRecord:
    """Queryable experiment metadata derived from one manifest."""

    experiment_id: str
    name: str
    hypothesis: str
    mode: ResearchMode
    status: ExperimentStatus
    dataset_version: str
    universe_version: str
    code_version: str
    config_schema_version: str
    hypothesis_family_id: str | None
    parent_experiment_id: str | None
    reproduction_of: str | None
    created_at: str
    completed_at: str | None
    manifest_checksum: str | None


class IndexedManifestStore:
    """Decorate any manifest store with a queryable experiment registry."""

    def __init__(self, store: ManifestStore, registry: ExperimentRegistry) -> None:
        self._store = store
        self._registry = registry

    def write_manifest(self, manifest: ExperimentManifest) -> None:
        """Persist the authoritative manifest, then index its checksum-verified representation."""

        self._store.write_manifest(manifest)
        persisted = self._store.read_manifest(manifest.experiment_id)
        self._registry.register(persisted)

    def write_stage_output(
        self,
        experiment_id: str,
        stage_name: str,
        output: dict[str, JSONValue],
    ) -> str:
        """Delegate analytical artifact persistence unchanged."""

        return self._store.write_stage_output(experiment_id, stage_name, output)

    def read_manifest(self, experiment_id: str) -> ExperimentManifest:
        """Read through to the authoritative manifest store."""

        return self._store.read_manifest(experiment_id)

    def read_stage_output(self, experiment_id: str, stage_name: str) -> dict[str, JSONValue]:
        """Read stage output through to the authoritative manifest store."""

        return self._store.read_stage_output(experiment_id, stage_name)


class DuckDBExperimentRegistry:
    """Persist and query compact experiment metadata in a local DuckDB database."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _registry_lock(path)
        self._ensure_schema()

    def register(self, manifest: ExperimentManifest) -> None:
        """Insert or update one experiment index row from its latest manifest state."""

        definition = manifest.definition
        values = (
            manifest.experiment_id,
            definition.name,
            definition.hypothesis,
            definition.mode.value,
            manifest.status.value,
            definition.dataset_version,
            definition.universe_version,
            definition.code_version,
            definition.config_schema_version,
            definition.hypothesis_family_id,
            definition.parent_experiment_id,
            manifest.reproduction_of,
            manifest.created_at,
            manifest.completed_at,
            manifest.manifest_checksum,
        )
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (experiment_id) DO UPDATE SET
                    name = excluded.name,
                    hypothesis = excluded.hypothesis,
                    mode = excluded.mode,
                    status = excluded.status,
                    dataset_version = excluded.dataset_version,
                    universe_version = excluded.universe_version,
                    code_version = excluded.code_version,
                    config_schema_version = excluded.config_schema_version,
                    hypothesis_family_id = excluded.hypothesis_family_id,
                    parent_experiment_id = excluded.parent_experiment_id,
                    reproduction_of = excluded.reproduction_of,
                    created_at = excluded.created_at,
                    completed_at = excluded.completed_at,
                    manifest_checksum = excluded.manifest_checksum
                """,
                values,
            )

    def get(self, experiment_id: str) -> ExperimentIndexRecord:
        """Return one indexed experiment or raise KeyError if it is unknown."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?", [experiment_id]
            ).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return _record_from_row(row)

    def query(
        self,
        *,
        status: ExperimentStatus | None = None,
        mode: ResearchMode | None = None,
        hypothesis_family_id: str | None = None,
        dataset_version: str | None = None,
    ) -> tuple[ExperimentIndexRecord, ...]:
        """Query experiments using deliberately narrow, auditable registry filters."""

        clauses: list[str] = []
        parameters: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if mode is not None:
            clauses.append("mode = ?")
            parameters.append(mode.value)
        if hypothesis_family_id is not None:
            clauses.append("hypothesis_family_id = ?")
            parameters.append(hypothesis_family_id)
        if dataset_version is not None:
            clauses.append("dataset_version = ?")
            parameters.append(dataset_version)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM experiments{where} ORDER BY created_at, experiment_id"
        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def lineage(self, experiment_id: str) -> tuple[ExperimentIndexRecord, ...]:
        """Return ancestors from the root experiment through the requested experiment."""

        records: list[ExperimentIndexRecord] = []
        seen: set[str] = set()
        current = self.get(experiment_id)
        while True:
            if current.experiment_id in seen:
                raise ValueError("experiment registry contains a lineage cycle")
            seen.add(current.experiment_id)
            records.append(current)
            parent_id = current.parent_experiment_id or current.reproduction_of
            if parent_id is None:
                break
            current = self.get(parent_id)
        records.reverse()
        return tuple(records)

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    hypothesis VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    dataset_version VARCHAR NOT NULL,
                    universe_version VARCHAR NOT NULL,
                    code_version VARCHAR NOT NULL,
                    config_schema_version VARCHAR NOT NULL,
                    hypothesis_family_id VARCHAR,
                    parent_experiment_id VARCHAR,
                    reproduction_of VARCHAR,
                    created_at VARCHAR NOT NULL,
                    completed_at VARCHAR,
                    manifest_checksum VARCHAR
                )
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Serialize connections to one registry file across the threaded local server."""

        with self._lock:
            connection = duckdb.connect(str(self._path))
            try:
                yield connection
            finally:
                connection.close()


def _registry_lock(path: Path) -> RLock:
    key = str(path.resolve())
    with _REGISTRY_LOCKS_GUARD:
        return _REGISTRY_LOCKS.setdefault(key, RLock())


def _record_from_row(row: tuple[object, ...]) -> ExperimentIndexRecord:
    return ExperimentIndexRecord(
        experiment_id=str(row[0]),
        name=str(row[1]),
        hypothesis=str(row[2]),
        mode=ResearchMode(str(row[3])),
        status=ExperimentStatus(str(row[4])),
        dataset_version=str(row[5]),
        universe_version=str(row[6]),
        code_version=str(row[7]),
        config_schema_version=str(row[8]),
        hypothesis_family_id=_optional_str(row[9]),
        parent_experiment_id=_optional_str(row[10]),
        reproduction_of=_optional_str(row[11]),
        created_at=str(row[12]),
        completed_at=_optional_str(row[13]),
        manifest_checksum=_optional_str(row[14]),
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)