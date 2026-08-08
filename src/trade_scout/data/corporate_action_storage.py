"""Immutable Parquet/DuckDB storage for canonical corporate-action datasets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import duckdb

from trade_scout.data.contracts import CorporateActionRecord, CorporateActionType, InstrumentId


class CorporateActionStorageError(RuntimeError):
    """Base error for canonical corporate-action storage."""


class CorporateActionDatasetConflictError(CorporateActionStorageError):
    """Raised when a version is reused with different corporate-action content/provenance."""


class CorporateActionDatasetIntegrityError(CorporateActionStorageError):
    """Raised when a registered corporate-action dataset fails integrity checks."""


class CorporateActionDatasetNotFoundError(CorporateActionStorageError):
    """Raised when a requested corporate-action dataset version is not registered."""


@dataclass(frozen=True, slots=True)
class CorporateActionPromotionRequest:
    """Version/provenance metadata required for one corporate-action promotion."""

    dataset_version: str
    primary_provider_id: str
    created_at: datetime
    source_batch_ids: tuple[str, ...]
    normalization_version: str
    instrument_snapshot_version: str

    def __post_init__(self) -> None:
        for name, value in (
            ("dataset_version", self.dataset_version),
            ("primary_provider_id", self.primary_provider_id),
            ("normalization_version", self.normalization_version),
            ("instrument_snapshot_version", self.instrument_snapshot_version),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if not self.source_batch_ids or any(not item.strip() for item in self.source_batch_ids):
            raise ValueError("source_batch_ids must contain non-empty batch IDs")
        if len(set(self.source_batch_ids)) != len(self.source_batch_ids):
            raise ValueError("source_batch_ids must not contain duplicates")


@dataclass(frozen=True, slots=True)
class CorporateActionDatasetManifest:
    """Registered immutable corporate-action dataset metadata."""

    dataset_version: str
    primary_provider_id: str
    created_at: datetime
    source_batch_ids: tuple[str, ...]
    normalization_version: str
    instrument_snapshot_version: str
    record_count: int
    first_effective_date: date | None
    last_effective_date: date | None
    logical_sha256: str
    parquet_sha256: str
    parquet_relative_path: str


class CorporateActionStore:
    """Promote and load canonical corporate actions with immutable version/provenance semantics."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.metadata_path = root / "metadata" / "datasets.duckdb"

    def promote(
        self,
        records: Iterable[CorporateActionRecord],
        request: CorporateActionPromotionRequest,
    ) -> CorporateActionDatasetManifest:
        """Write a canonical action dataset only if identity and provenance are unambiguous."""

        canonical = tuple(
            sorted(
                records,
                key=lambda item: (
                    item.effective_date,
                    str(item.instrument_id),
                    str(item.action_type),
                    item.action_id,
                ),
            )
        )
        _validate_records(canonical, primary_provider_id=request.primary_provider_id)
        logical = _logical_checksum([_record_payload(item) for item in canonical])
        existing = self._get_manifest_or_none(request.dataset_version)
        if existing is not None:
            expected = _promotion_identity(
                request,
                record_count=len(canonical),
                first_effective_date=canonical[0].effective_date if canonical else None,
                last_effective_date=canonical[-1].effective_date if canonical else None,
                logical_sha256=logical,
            )
            if _registered_identity(existing) != expected:
                raise CorporateActionDatasetConflictError(
                    f"corporate-action dataset {request.dataset_version} already exists with "
                    "different content/provenance"
                )
            self._verify_file(existing)
            return existing

        relative = (
            Path("canonical")
            / "corporate_actions"
            / request.dataset_version
            / "corporate_actions.parquet"
        )
        path = self.root / relative
        if path.exists():
            raise CorporateActionDatasetConflictError(
                "unregistered corporate-action Parquet already exists for this version"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            _write_parquet(path, canonical)
            manifest = CorporateActionDatasetManifest(
                dataset_version=request.dataset_version,
                primary_provider_id=request.primary_provider_id,
                created_at=request.created_at,
                source_batch_ids=request.source_batch_ids,
                normalization_version=request.normalization_version,
                instrument_snapshot_version=request.instrument_snapshot_version,
                record_count=len(canonical),
                first_effective_date=canonical[0].effective_date if canonical else None,
                last_effective_date=canonical[-1].effective_date if canonical else None,
                logical_sha256=logical,
                parquet_sha256=_file_sha256(path),
                parquet_relative_path=relative.as_posix(),
            )
            self._register(manifest)
        except Exception:
            if self._get_manifest_or_none(request.dataset_version) is None:
                path.unlink(missing_ok=True)
            raise
        return manifest

    def get_manifest(self, dataset_version: str) -> CorporateActionDatasetManifest:
        manifest = self._get_manifest_or_none(dataset_version)
        if manifest is None:
            raise CorporateActionDatasetNotFoundError(
                f"unknown corporate-action dataset {dataset_version}"
            )
        return manifest

    def load(self, dataset_version: str) -> tuple[CorporateActionRecord, ...]:
        """Load a registered canonical action dataset after physical/logical integrity checks."""

        manifest = self.get_manifest(dataset_version)
        self._verify_file(manifest)
        records = _read_parquet(self.root / manifest.parquet_relative_path)
        _validate_records(records, primary_provider_id=manifest.primary_provider_id)
        if (
            _logical_checksum([_record_payload(item) for item in records])
            != manifest.logical_sha256
        ):
            raise CorporateActionDatasetIntegrityError("corporate-action logical checksum mismatch")
        return records

    def _register(self, manifest: CorporateActionDatasetManifest) -> None:
        self._initialize_registry()
        with duckdb.connect(str(self.metadata_path)) as connection:
            connection.execute(
                """
                INSERT INTO corporate_action_versions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    manifest.dataset_version,
                    manifest.primary_provider_id,
                    manifest.created_at.isoformat(),
                    json.dumps(manifest.source_batch_ids),
                    manifest.normalization_version,
                    manifest.instrument_snapshot_version,
                    manifest.record_count,
                    manifest.first_effective_date,
                    manifest.last_effective_date,
                    manifest.logical_sha256,
                    manifest.parquet_sha256,
                    manifest.parquet_relative_path,
                    datetime.now(manifest.created_at.tzinfo).isoformat(),
                ),
            )

    def _get_manifest_or_none(self, dataset_version: str) -> CorporateActionDatasetManifest | None:
        if not self.metadata_path.exists():
            return None
        self._initialize_registry()
        with duckdb.connect(str(self.metadata_path), read_only=True) as connection:
            row = connection.execute(
                """
                SELECT dataset_version, primary_provider_id, created_at, source_batch_ids,
                       normalization_version, instrument_snapshot_version, record_count,
                       first_effective_date, last_effective_date, logical_sha256, parquet_sha256,
                       parquet_relative_path
                FROM corporate_action_versions WHERE dataset_version = ?
                """,
                (dataset_version,),
            ).fetchone()
        return None if row is None else _manifest_from_row(row)

    def _initialize_registry(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.metadata_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_action_versions (
                    dataset_version VARCHAR PRIMARY KEY,
                    primary_provider_id VARCHAR NOT NULL,
                    created_at VARCHAR NOT NULL,
                    source_batch_ids VARCHAR NOT NULL,
                    normalization_version VARCHAR NOT NULL,
                    instrument_snapshot_version VARCHAR NOT NULL,
                    record_count BIGINT NOT NULL,
                    first_effective_date DATE,
                    last_effective_date DATE,
                    logical_sha256 VARCHAR NOT NULL,
                    parquet_sha256 VARCHAR NOT NULL,
                    parquet_relative_path VARCHAR NOT NULL,
                    registered_at VARCHAR NOT NULL
                )
                """
            )

    def _verify_file(self, manifest: CorporateActionDatasetManifest) -> None:
        path = self.root / manifest.parquet_relative_path
        if not path.is_file():
            raise CorporateActionDatasetIntegrityError(
                "registered corporate-action Parquet file is missing"
            )
        if _file_sha256(path) != manifest.parquet_sha256:
            raise CorporateActionDatasetIntegrityError("corporate-action Parquet checksum mismatch")


def _validate_records(
    records: tuple[CorporateActionRecord, ...],
    *,
    primary_provider_id: str,
) -> None:
    seen_ids: dict[str, CorporateActionRecord] = {}
    seen_source_events: dict[tuple[str, str], str] = {}
    for record in records:
        if not record.action_id.strip():
            raise CorporateActionDatasetIntegrityError("action_id must be non-empty")
        if record.provider_id != primary_provider_id:
            raise CorporateActionDatasetIntegrityError(
                f"action {record.action_id} uses provider {record.provider_id}; "
                f"expected {primary_provider_id}"
            )
        existing = seen_ids.get(record.action_id)
        if existing is not None:
            if existing != record:
                raise CorporateActionDatasetIntegrityError(
                    f"action_id {record.action_id} has conflicting records"
                )
            raise CorporateActionDatasetIntegrityError(
                f"duplicate corporate-action record {record.action_id}"
            )
        seen_ids[record.action_id] = record
        if record.source_event_id is not None:
            key = (record.provider_id, record.source_event_id)
            owner = seen_source_events.get(key)
            if owner is not None and owner != record.action_id:
                raise CorporateActionDatasetIntegrityError(
                    f"provider source event {key[0]}:{key[1]} maps to multiple action IDs"
                )
            seen_source_events[key] = record.action_id


def _write_parquet(path: Path, records: tuple[CorporateActionRecord, ...]) -> None:
    with duckdb.connect() as connection:
        connection.execute(
            """
            CREATE TABLE corporate_actions (
                action_id VARCHAR, instrument_id VARCHAR, action_type VARCHAR,
                effective_date DATE, provider_id VARCHAR, source_event_id VARCHAR,
                source_fields_json VARCHAR
            )
            """
        )
        if records:
            connection.executemany(
                "INSERT INTO corporate_actions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.action_id,
                        str(item.instrument_id),
                        str(item.action_type),
                        item.effective_date,
                        item.provider_id,
                        item.source_event_id,
                        _source_fields_json(item.source_fields),
                    )
                    for item in records
                ],
            )
        connection.execute(f"COPY corporate_actions TO {_sql_literal(path)} (FORMAT PARQUET)")


def _read_parquet(path: Path) -> tuple[CorporateActionRecord, ...]:
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            SELECT action_id, instrument_id, action_type, effective_date, provider_id,
                   source_event_id, source_fields_json
            FROM read_parquet(?)
            ORDER BY effective_date, instrument_id, action_type, action_id
            """,
            (str(path),),
        ).fetchall()
    return tuple(_record_from_row(row) for row in rows)


def _record_from_row(row: tuple[object, ...]) -> CorporateActionRecord:
    source_fields = json.loads(str(row[6]))
    if not isinstance(source_fields, dict) or not all(
        isinstance(key, str) and (value is None or isinstance(value, str | int | float | bool))
        for key, value in source_fields.items()
    ):
        raise CorporateActionDatasetIntegrityError("corporate-action source_fields_json is invalid")
    effective_date = row[3]
    if not isinstance(effective_date, date):
        raise CorporateActionDatasetIntegrityError("corporate-action effective_date is invalid")
    return CorporateActionRecord(
        action_id=str(row[0]),
        instrument_id=InstrumentId(str(row[1])),
        action_type=CorporateActionType(str(row[2])),
        effective_date=effective_date,
        provider_id=str(row[4]),
        source_event_id=None if row[5] is None else str(row[5]),
        source_fields=MappingProxyType(source_fields),
    )


def _record_payload(record: CorporateActionRecord) -> dict[str, Any]:
    return {
        "action_id": record.action_id,
        "instrument_id": str(record.instrument_id),
        "action_type": str(record.action_type),
        "effective_date": record.effective_date.isoformat(),
        "provider_id": record.provider_id,
        "source_event_id": record.source_event_id,
        "source_fields": dict(sorted(record.source_fields.items())),
    }


def _promotion_identity(
    request: CorporateActionPromotionRequest,
    *,
    record_count: int,
    first_effective_date: date | None,
    last_effective_date: date | None,
    logical_sha256: str,
) -> tuple[object, ...]:
    return (
        request.dataset_version,
        request.primary_provider_id,
        request.created_at,
        request.source_batch_ids,
        request.normalization_version,
        request.instrument_snapshot_version,
        record_count,
        first_effective_date,
        last_effective_date,
        logical_sha256,
    )


def _registered_identity(manifest: CorporateActionDatasetManifest) -> tuple[object, ...]:
    return (
        manifest.dataset_version,
        manifest.primary_provider_id,
        manifest.created_at,
        manifest.source_batch_ids,
        manifest.normalization_version,
        manifest.instrument_snapshot_version,
        manifest.record_count,
        manifest.first_effective_date,
        manifest.last_effective_date,
        manifest.logical_sha256,
    )


def _manifest_from_row(row: tuple[object, ...]) -> CorporateActionDatasetManifest:
    source_ids = json.loads(str(row[3]))
    if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
        raise CorporateActionDatasetIntegrityError("registered source_batch_ids are invalid")
    try:
        created_at = datetime.fromisoformat(str(row[2]))
    except ValueError as exc:
        raise CorporateActionDatasetIntegrityError("registered created_at is invalid") from exc
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise CorporateActionDatasetIntegrityError("registered created_at is not timezone-aware")
    return CorporateActionDatasetManifest(
        dataset_version=str(row[0]),
        primary_provider_id=str(row[1]),
        created_at=created_at,
        source_batch_ids=tuple(source_ids),
        normalization_version=str(row[4]),
        instrument_snapshot_version=str(row[5]),
        record_count=_required_int(row[6], "record_count"),
        first_effective_date=_optional_date(row[7]),
        last_effective_date=_optional_date(row[8]),
        logical_sha256=str(row[9]),
        parquet_sha256=str(row[10]),
        parquet_relative_path=str(row[11]),
    )


def _source_fields_json(fields: dict[str, Any] | Any) -> str:
    return json.dumps(dict(fields), sort_keys=True, separators=(",", ":"))


def _logical_checksum(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CorporateActionDatasetIntegrityError(f"registered {field} is invalid")
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, date):
        raise CorporateActionDatasetIntegrityError("registered effective-date value is invalid")
    return value
