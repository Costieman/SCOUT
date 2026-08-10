"""Immutable Parquet/DuckDB storage for versioned feature observations."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

import duckdb

from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.features.contracts import (
    FeatureAvailabilityStatus,
    FeatureParameter,
    FeatureValue,
)

_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class FeatureSnapshotConflictError(RuntimeError):
    """Raised when an immutable feature snapshot identity is reused with different content."""


class FeatureSnapshotIntegrityError(RuntimeError):
    """Raised when registered feature output fails physical or logical verification."""


class FeatureSnapshotNotFoundError(KeyError):
    """Raised when a requested feature snapshot is not registered."""


@dataclass(frozen=True, slots=True)
class FeatureSnapshotPromotionRequest:
    """Provenance required to promote one deterministic derived feature snapshot."""

    dataset_version: DatasetVersion
    feature_set_version: str
    created_at: datetime
    source_canonical_content_sha256: str
    feature_definition_sha256: str

    def __post_init__(self) -> None:
        _validate_version(str(self.dataset_version), "dataset_version")
        _validate_version(self.feature_set_version, "feature_set_version")
        _validate_hash(self.source_canonical_content_sha256, "source_canonical_content_sha256")
        _validate_hash(self.feature_definition_sha256, "feature_definition_sha256")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class FeatureSnapshotManifest:
    """Immutable metadata for one feature-set materialization over one canonical dataset."""

    dataset_version: DatasetVersion
    feature_set_version: str
    created_at: datetime
    source_canonical_content_sha256: str
    feature_definition_sha256: str
    record_count: int
    available_count: int
    warmup_count: int
    input_unavailable_count: int
    first_trade_date: date
    last_trade_date: date
    content_checksum_sha256: str
    parquet_checksum_sha256: str
    parquet_relative_path: str


class FeatureSnapshotStore:
    """Promote, verify, and reload immutable feature observations."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.derived_root = root / "derived" / "features"
        self.metadata_path = root / "metadata" / "features.duckdb"

    def promote(
        self,
        values: Iterable[FeatureValue],
        request: FeatureSnapshotPromotionRequest,
    ) -> FeatureSnapshotManifest:
        """Atomically register a deterministic feature snapshot or return its identical prior copy."""

        materialized = tuple(
            sorted(
                values,
                key=lambda item: (
                    str(item.instrument_id),
                    item.trade_date,
                    item.feature_name,
                    item.feature_version,
                ),
            )
        )
        if not materialized:
            raise ValueError("feature snapshot promotion requires at least one observation")
        _validate_values(materialized, request)
        content_checksum = _logical_checksum(materialized)
        target = self._snapshot_directory(request.dataset_version, request.feature_set_version)
        existing = self.get_manifest(request.dataset_version, request.feature_set_version)
        if existing is not None:
            if not target.exists():
                raise FeatureSnapshotIntegrityError("registered feature snapshot directory is missing")
            self._verify_parquet(existing)
            if _same_promotion(existing, request, content_checksum):
                return existing
            raise FeatureSnapshotConflictError(
                "feature snapshot identity already exists with different content or provenance"
            )
        if target.exists():
            raise FeatureSnapshotConflictError("unregistered feature snapshot directory already exists")

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{request.feature_set_version}.", dir=target.parent))
        parquet = temporary / "features.parquet"
        try:
            _write_parquet(materialized, parquet)
            _verify_parquet_row_count(parquet, expected=len(materialized))
            relative = str(
                Path("derived")
                / "features"
                / str(request.dataset_version)
                / request.feature_set_version
                / "features.parquet"
            )
            counts = _availability_counts(materialized)
            manifest = FeatureSnapshotManifest(
                dataset_version=request.dataset_version,
                feature_set_version=request.feature_set_version,
                created_at=request.created_at,
                source_canonical_content_sha256=request.source_canonical_content_sha256,
                feature_definition_sha256=request.feature_definition_sha256,
                record_count=len(materialized),
                available_count=counts[FeatureAvailabilityStatus.AVAILABLE],
                warmup_count=counts[FeatureAvailabilityStatus.WARMUP],
                input_unavailable_count=counts[FeatureAvailabilityStatus.INPUT_UNAVAILABLE],
                first_trade_date=min(item.trade_date for item in materialized),
                last_trade_date=max(item.trade_date for item in materialized),
                content_checksum_sha256=content_checksum,
                parquet_checksum_sha256=_file_checksum(parquet),
                parquet_relative_path=relative,
            )
            temporary.rename(target)
            try:
                self._register_manifest(manifest)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            return manifest
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def get_manifest(
        self,
        dataset_version: DatasetVersion,
        feature_set_version: str,
    ) -> FeatureSnapshotManifest | None:
        """Return a registered feature manifest without reading feature values."""

        connection = self._connect_metadata()
        try:
            row = connection.execute(
                """
                SELECT dataset_version, feature_set_version, created_at,
                       source_canonical_content_sha256, feature_definition_sha256,
                       record_count, available_count, warmup_count, input_unavailable_count,
                       first_trade_date, last_trade_date, content_checksum_sha256,
                       parquet_checksum_sha256, parquet_relative_path
                FROM feature_snapshots
                WHERE dataset_version = ? AND feature_set_version = ?
                """,
                [str(dataset_version), feature_set_version],
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _manifest_from_row(row)

    def load(
        self,
        dataset_version: DatasetVersion,
        feature_set_version: str,
    ) -> tuple[FeatureValue, ...]:
        """Load a feature snapshot only after checksum verification."""

        manifest = self.get_manifest(dataset_version, feature_set_version)
        if manifest is None:
            raise FeatureSnapshotNotFoundError(f"{dataset_version}:{feature_set_version}")
        parquet = self._verify_parquet(manifest)
        connection = duckdb.connect()
        try:
            rows = connection.execute(
                f"""
                SELECT instrument_id, trade_date, feature_name, feature_version,
                       resolved_parameters_json, value, units, availability_status,
                       dataset_version, feature_set_version
                FROM read_parquet({_sql_literal(parquet)})
                ORDER BY instrument_id, trade_date, feature_name, feature_version
                """
            ).fetchall()
        finally:
            connection.close()
        values = tuple(_feature_value_from_row(row) for row in rows)
        if _logical_checksum(values) != manifest.content_checksum_sha256:
            raise FeatureSnapshotIntegrityError("feature snapshot logical checksum mismatch")
        return values

    def _snapshot_directory(
        self,
        dataset_version: DatasetVersion,
        feature_set_version: str,
    ) -> Path:
        _validate_version(str(dataset_version), "dataset_version")
        _validate_version(feature_set_version, "feature_set_version")
        return self.derived_root / str(dataset_version) / feature_set_version

    def _connect_metadata(self) -> duckdb.DuckDBPyConnection:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(self.metadata_path))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_snapshots (
                dataset_version VARCHAR NOT NULL,
                feature_set_version VARCHAR NOT NULL,
                created_at VARCHAR NOT NULL,
                source_canonical_content_sha256 VARCHAR NOT NULL,
                feature_definition_sha256 VARCHAR NOT NULL,
                record_count BIGINT NOT NULL,
                available_count BIGINT NOT NULL,
                warmup_count BIGINT NOT NULL,
                input_unavailable_count BIGINT NOT NULL,
                first_trade_date DATE NOT NULL,
                last_trade_date DATE NOT NULL,
                content_checksum_sha256 VARCHAR NOT NULL,
                parquet_checksum_sha256 VARCHAR NOT NULL,
                parquet_relative_path VARCHAR NOT NULL,
                PRIMARY KEY (dataset_version, feature_set_version)
            )
            """
        )
        return connection

    def _register_manifest(self, manifest: FeatureSnapshotManifest) -> None:
        connection = self._connect_metadata()
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                """
                INSERT INTO feature_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(manifest.dataset_version),
                    manifest.feature_set_version,
                    manifest.created_at.isoformat(),
                    manifest.source_canonical_content_sha256,
                    manifest.feature_definition_sha256,
                    manifest.record_count,
                    manifest.available_count,
                    manifest.warmup_count,
                    manifest.input_unavailable_count,
                    manifest.first_trade_date,
                    manifest.last_trade_date,
                    manifest.content_checksum_sha256,
                    manifest.parquet_checksum_sha256,
                    manifest.parquet_relative_path,
                ],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _verify_parquet(self, manifest: FeatureSnapshotManifest) -> Path:
        path = self.root / manifest.parquet_relative_path
        if not path.is_file():
            raise FeatureSnapshotIntegrityError("feature Parquet file is missing")
        if _file_checksum(path) != manifest.parquet_checksum_sha256:
            raise FeatureSnapshotIntegrityError("feature Parquet checksum mismatch")
        _verify_parquet_row_count(path, expected=manifest.record_count)
        return path


def _validate_values(
    values: tuple[FeatureValue, ...],
    request: FeatureSnapshotPromotionRequest,
) -> None:
    seen: set[tuple[str, date, str, str]] = set()
    for item in values:
        if item.dataset_version != request.dataset_version:
            raise FeatureSnapshotConflictError("feature value dataset version mismatches promotion request")
        if item.feature_set_version != request.feature_set_version:
            raise FeatureSnapshotConflictError("feature value set version mismatches promotion request")
        key = (str(item.instrument_id), item.trade_date, item.feature_name, item.feature_version)
        if key in seen:
            raise FeatureSnapshotConflictError(f"duplicate feature observation: {key}")
        seen.add(key)
        if item.value is not None and not math_is_finite(item.value):
            raise FeatureSnapshotIntegrityError("available feature value must be finite")


def _availability_counts(
    values: tuple[FeatureValue, ...],
) -> dict[FeatureAvailabilityStatus, int]:
    counts = {status: 0 for status in FeatureAvailabilityStatus}
    for item in values:
        counts[item.availability_status] += 1
    return counts


def _write_parquet(values: tuple[FeatureValue, ...], path: Path) -> None:
    connection = duckdb.connect()
    try:
        connection.execute(
            """
            CREATE TEMP TABLE feature_stage (
                instrument_id VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                feature_name VARCHAR NOT NULL,
                feature_version VARCHAR NOT NULL,
                resolved_parameters_json VARCHAR NOT NULL,
                value DOUBLE,
                units VARCHAR NOT NULL,
                availability_status VARCHAR NOT NULL,
                dataset_version VARCHAR NOT NULL,
                feature_set_version VARCHAR NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO feature_stage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [_feature_row(item) for item in values],
        )
        connection.execute(
            f"""
            COPY (
                SELECT * FROM feature_stage
                ORDER BY instrument_id, trade_date, feature_name, feature_version
            ) TO {_sql_literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
    finally:
        connection.close()


def _feature_row(item: FeatureValue) -> tuple[object, ...]:
    return (
        str(item.instrument_id),
        item.trade_date,
        item.feature_name,
        item.feature_version,
        json.dumps(dict(sorted(item.resolved_parameters.items())), separators=(",", ":")),
        item.value,
        item.units,
        item.availability_status.value,
        str(item.dataset_version),
        item.feature_set_version,
    )


def _feature_value_from_row(row: tuple[object, ...]) -> FeatureValue:
    raw_parameters: object = json.loads(str(row[4]))
    if not isinstance(raw_parameters, dict):
        raise FeatureSnapshotIntegrityError("feature parameters payload is not an object")
    parameters: dict[str, FeatureParameter] = {}
    for key, value in raw_parameters.items():
        if not isinstance(key, str) or not isinstance(value, str | int | float | bool):
            raise FeatureSnapshotIntegrityError("feature parameters payload contains invalid values")
        parameters[key] = value
    value = None if row[5] is None else float(row[5])
    return FeatureValue(
        instrument_id=InstrumentId(str(row[0])),
        trade_date=_require_date(row[1]),
        feature_name=str(row[2]),
        feature_version=str(row[3]),
        resolved_parameters=MappingProxyType(parameters),
        value=value,
        units=str(row[6]),
        availability_status=FeatureAvailabilityStatus(str(row[7])),
        dataset_version=DatasetVersion(str(row[8])),
        feature_set_version=str(row[9]),
    )


def _logical_checksum(values: tuple[FeatureValue, ...]) -> str:
    digest = hashlib.sha256()
    for item in values:
        payload = [
            str(item.instrument_id),
            item.trade_date.isoformat(),
            item.feature_name,
            item.feature_version,
            dict(sorted(item.resolved_parameters.items())),
            item.value,
            item.units,
            item.availability_status.value,
            str(item.dataset_version),
            item.feature_set_version,
        ]
        digest.update(
            json.dumps(payload, sort_keys=True, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _same_promotion(
    manifest: FeatureSnapshotManifest,
    request: FeatureSnapshotPromotionRequest,
    content_checksum: str,
) -> bool:
    return (
        manifest.dataset_version == request.dataset_version
        and manifest.feature_set_version == request.feature_set_version
        and manifest.created_at == request.created_at
        and manifest.source_canonical_content_sha256 == request.source_canonical_content_sha256
        and manifest.feature_definition_sha256 == request.feature_definition_sha256
        and manifest.content_checksum_sha256 == content_checksum
    )


def _manifest_from_row(row: tuple[object, ...]) -> FeatureSnapshotManifest:
    return FeatureSnapshotManifest(
        dataset_version=DatasetVersion(str(row[0])),
        feature_set_version=str(row[1]),
        created_at=_require_datetime(str(row[2])),
        source_canonical_content_sha256=str(row[3]),
        feature_definition_sha256=str(row[4]),
        record_count=int(row[5]),
        available_count=int(row[6]),
        warmup_count=int(row[7]),
        input_unavailable_count=int(row[8]),
        first_trade_date=_require_date(row[9]),
        last_trade_date=_require_date(row[10]),
        content_checksum_sha256=str(row[11]),
        parquet_checksum_sha256=str(row[12]),
        parquet_relative_path=str(row[13]),
    )


def _verify_parquet_row_count(path: Path, *, expected: int) -> None:
    connection = duckdb.connect()
    try:
        row = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(path)})"
        ).fetchone()
    finally:
        connection.close()
    if row is None or int(row[0]) != expected:
        raise FeatureSnapshotIntegrityError("feature Parquet row-count verification failed")


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _validate_version(value: str, field: str) -> None:
    if _SAFE_VERSION.fullmatch(value) is None:
        raise ValueError(f"{field} contains unsupported path characters")


def _validate_hash(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError(f"{field} must be a SHA-256 hex digest")


def _require_date(value: object) -> date:
    if isinstance(value, date):
        return value
    raise FeatureSnapshotIntegrityError("feature snapshot contains invalid trade_date")


def _require_datetime(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FeatureSnapshotIntegrityError("feature manifest contains invalid created_at") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise FeatureSnapshotIntegrityError("feature manifest created_at is not timezone-aware")
    return result


def math_is_finite(value: float) -> bool:
    """Keep the storage boundary dependency-light while rejecting NaN/inf."""

    return value == value and value not in (float("inf"), float("-inf"))


__all__ = [
    "FeatureSnapshotConflictError",
    "FeatureSnapshotIntegrityError",
    "FeatureSnapshotManifest",
    "FeatureSnapshotNotFoundError",
    "FeatureSnapshotPromotionRequest",
    "FeatureSnapshotStore",
]
