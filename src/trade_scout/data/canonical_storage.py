"""Immutable canonical daily-bar storage backed by Parquet and DuckDB metadata."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import duckdb

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.quality import validate_daily_bars

_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_BLOCKED_QUALITY_STATES = frozenset({QualityStatus.QUARANTINE, QualityStatus.REJECT})


class DatasetVersionConflictError(RuntimeError):
    """Raised when an immutable dataset version is reused with different content or provenance."""


class DatasetPromotionQualityError(ValueError):
    """Raised when records that are not research-ready are submitted for promotion."""


class CanonicalDatasetIntegrityError(RuntimeError):
    """Raised when stored canonical data do not match their registered integrity metadata."""


class CanonicalDatasetNotFoundError(KeyError):
    """Raised when a requested canonical dataset version has not been registered."""


@dataclass(frozen=True, slots=True)
class DatasetQualitySummary:
    """Quality-state counts captured in an immutable dataset manifest."""

    pass_count: int
    warn_count: int
    quarantine_count: int
    reject_count: int


@dataclass(frozen=True, slots=True)
class DatasetPromotionRequest:
    """Provenance and definition versions required to create one canonical dataset version."""

    dataset_id: str
    dataset_version: DatasetVersion
    primary_provider_id: str
    created_at: datetime
    source_batch_ids: tuple[str, ...]
    transformation_version: str
    adjustment_policy_version: str
    universe_construction_version: str
    quality_check_version: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.dataset_id, field="dataset_id")
        _validate_version(str(self.dataset_version))
        _validate_non_empty(self.primary_provider_id, field="primary_provider_id")
        _validate_aware_datetime(self.created_at)
        _validate_non_empty(self.transformation_version, field="transformation_version")
        _validate_non_empty(self.adjustment_policy_version, field="adjustment_policy_version")
        _validate_non_empty(
            self.universe_construction_version,
            field="universe_construction_version",
        )
        _validate_non_empty(self.quality_check_version, field="quality_check_version")
        if len(set(self.source_batch_ids)) != len(self.source_batch_ids):
            raise ValueError("source_batch_ids must not contain duplicates")
        for batch_id in self.source_batch_ids:
            _validate_non_empty(batch_id, field="source_batch_id")


@dataclass(frozen=True, slots=True)
class CanonicalDatasetManifest:
    """Immutable registry record for one research-ready canonical daily-bar dataset."""

    dataset_id: str
    dataset_version: DatasetVersion
    created_at: datetime
    primary_provider_id: str
    source_batch_ids: tuple[str, ...]
    transformation_version: str
    adjustment_policy_version: str
    universe_construction_version: str
    quality_check_version: str
    quality_summary: DatasetQualitySummary
    record_count: int
    first_trade_date: date
    last_trade_date: date
    content_checksum_sha256: str
    parquet_checksum_sha256: str
    parquet_relative_path: str


class CanonicalDailyBarStore:
    """Promote, register, verify, and read immutable canonical daily-bar dataset versions."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.canonical_root = root / "canonical" / "equities_daily"
        self.metadata_path = root / "metadata" / "datasets.duckdb"

    def promote(
        self,
        bars: Iterable[DailyBar],
        request: DatasetPromotionRequest,
    ) -> CanonicalDatasetManifest:
        """Promote quality-approved bars into a versioned Parquet dataset and DuckDB registry."""

        materialized = tuple(
            sorted(bars, key=lambda bar: (str(bar.instrument_id), bar.trade_date, bar.provider_id))
        )
        if not materialized:
            raise ValueError("canonical promotion requires at least one daily bar")

        self._validate_promotion_input(materialized, request)
        quality_summary = _quality_summary(materialized)
        content_checksum = _logical_checksum(materialized)
        target_directory = self._dataset_directory(request.dataset_version)

        existing = self.get_manifest(request.dataset_version)
        if existing is not None:
            if not target_directory.exists():
                raise CanonicalDatasetIntegrityError(
                    f"registered dataset {request.dataset_version} is missing "
                    "its canonical directory"
                )
            self._verify_parquet_file(existing)
            if _same_promotion(existing, request, content_checksum):
                return existing
            raise DatasetVersionConflictError(
                f"dataset version {request.dataset_version} already exists with different "
                "content or provenance"
            )
        if target_directory.exists():
            raise DatasetVersionConflictError(
                f"unregistered canonical directory already exists for {request.dataset_version}"
            )

        target_directory.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{request.dataset_version}.",
                dir=target_directory.parent,
            )
        )
        temporary_parquet = temporary / "daily_bars.parquet"
        try:
            self._write_parquet(materialized, temporary_parquet)
            _verify_parquet_row_count(temporary_parquet, expected=len(materialized))
            parquet_checksum = _file_checksum(temporary_parquet)
            relative_path = str(
                Path("canonical")
                / "equities_daily"
                / str(request.dataset_version)
                / "daily_bars.parquet"
            )
            manifest = CanonicalDatasetManifest(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                created_at=request.created_at,
                primary_provider_id=request.primary_provider_id,
                source_batch_ids=request.source_batch_ids,
                transformation_version=request.transformation_version,
                adjustment_policy_version=request.adjustment_policy_version,
                universe_construction_version=request.universe_construction_version,
                quality_check_version=request.quality_check_version,
                quality_summary=quality_summary,
                record_count=len(materialized),
                first_trade_date=min(bar.trade_date for bar in materialized),
                last_trade_date=max(bar.trade_date for bar in materialized),
                content_checksum_sha256=content_checksum,
                parquet_checksum_sha256=parquet_checksum,
                parquet_relative_path=relative_path,
            )

            temporary.rename(target_directory)
            try:
                self._register_manifest(manifest)
            except Exception:
                shutil.rmtree(target_directory, ignore_errors=True)
                raise
            return manifest
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def get_manifest(self, dataset_version: DatasetVersion) -> CanonicalDatasetManifest | None:
        """Return one registered dataset manifest, if present."""

        connection = self._connect_metadata()
        try:
            row = connection.execute(
                """
                SELECT
                    dataset_id,
                    dataset_version,
                    created_at,
                    primary_provider_id,
                    source_batch_ids_json,
                    transformation_version,
                    adjustment_policy_version,
                    universe_construction_version,
                    quality_check_version,
                    pass_count,
                    warn_count,
                    quarantine_count,
                    reject_count,
                    record_count,
                    first_trade_date,
                    last_trade_date,
                    content_checksum_sha256,
                    parquet_checksum_sha256,
                    parquet_relative_path
                FROM dataset_versions
                WHERE dataset_version = ?
                """,
                [str(dataset_version)],
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _manifest_from_row(row)

    def load(self, dataset_version: DatasetVersion) -> tuple[DailyBar, ...]:
        """Read a registered dataset only after verifying the stored Parquet checksum."""

        manifest = self.get_manifest(dataset_version)
        if manifest is None:
            raise CanonicalDatasetNotFoundError(str(dataset_version))
        parquet_path = self._verify_parquet_file(manifest)

        connection = duckdb.connect()
        try:
            rows = connection.execute(
                f"""
                SELECT
                    instrument_id,
                    trade_date,
                    open_raw,
                    high_raw,
                    low_raw,
                    close_raw,
                    volume_raw,
                    split_factor,
                    dividend_cash,
                    open_split_adjusted,
                    high_split_adjusted,
                    low_split_adjusted,
                    close_split_adjusted,
                    provider_id,
                    dataset_version,
                    quality_status
                FROM read_parquet({_sql_literal(parquet_path)})
                ORDER BY instrument_id, trade_date, provider_id
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(_daily_bar_from_row(row) for row in rows)

    def _validate_promotion_input(
        self,
        bars: tuple[DailyBar, ...],
        request: DatasetPromotionRequest,
    ) -> None:
        report = validate_daily_bars(bars)
        if report.status in _BLOCKED_QUALITY_STATES:
            raise DatasetPromotionQualityError(
                f"daily-bar validation status {report.status} blocks canonical promotion"
            )

        for bar in bars:
            if bar.dataset_version != request.dataset_version:
                raise DatasetVersionConflictError(
                    f"bar dataset version {bar.dataset_version} does not match promotion version "
                    f"{request.dataset_version}"
                )
            if bar.provider_id != request.primary_provider_id:
                raise DatasetVersionConflictError(
                    f"bar provider {bar.provider_id} does not match canonical provider "
                    f"{request.primary_provider_id}"
                )
            if bar.quality_status in _BLOCKED_QUALITY_STATES:
                raise DatasetPromotionQualityError(
                    f"{bar.instrument_id} on {bar.trade_date} has blocked quality state "
                    f"{bar.quality_status}"
                )

    def _dataset_directory(self, dataset_version: DatasetVersion) -> Path:
        _validate_version(str(dataset_version))
        return self.canonical_root / str(dataset_version)

    def _write_parquet(self, bars: tuple[DailyBar, ...], path: Path) -> None:
        connection = duckdb.connect()
        try:
            connection.execute(
                """
                CREATE TEMP TABLE canonical_daily_bars_stage (
                    instrument_id VARCHAR NOT NULL,
                    trade_date DATE NOT NULL,
                    open_raw DOUBLE NOT NULL,
                    high_raw DOUBLE NOT NULL,
                    low_raw DOUBLE NOT NULL,
                    close_raw DOUBLE NOT NULL,
                    volume_raw DOUBLE NOT NULL,
                    split_factor DOUBLE NOT NULL,
                    dividend_cash DOUBLE NOT NULL,
                    open_split_adjusted DOUBLE,
                    high_split_adjusted DOUBLE,
                    low_split_adjusted DOUBLE,
                    close_split_adjusted DOUBLE,
                    provider_id VARCHAR NOT NULL,
                    dataset_version VARCHAR NOT NULL,
                    quality_status VARCHAR NOT NULL
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO canonical_daily_bars_stage VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [_daily_bar_row(bar) for bar in bars],
            )
            connection.execute(
                f"""
                COPY (
                    SELECT *
                    FROM canonical_daily_bars_stage
                    ORDER BY instrument_id, trade_date, provider_id
                )
                TO {_sql_literal(path)}
                (FORMAT PARQUET, COMPRESSION ZSTD)
                """
            )
        finally:
            connection.close()

    def _connect_metadata(self) -> duckdb.DuckDBPyConnection:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(self.metadata_path))
        _ensure_metadata_schema(connection)
        return connection

    def _register_manifest(self, manifest: CanonicalDatasetManifest) -> None:
        connection = self._connect_metadata()
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                """
                INSERT INTO dataset_versions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    manifest.dataset_id,
                    str(manifest.dataset_version),
                    manifest.created_at.isoformat(),
                    manifest.primary_provider_id,
                    json.dumps(manifest.source_batch_ids, separators=(",", ":")),
                    manifest.transformation_version,
                    manifest.adjustment_policy_version,
                    manifest.universe_construction_version,
                    manifest.quality_check_version,
                    manifest.quality_summary.pass_count,
                    manifest.quality_summary.warn_count,
                    manifest.quality_summary.quarantine_count,
                    manifest.quality_summary.reject_count,
                    manifest.record_count,
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

    def _verify_parquet_file(self, manifest: CanonicalDatasetManifest) -> Path:
        path = self.root / manifest.parquet_relative_path
        if not path.is_file():
            raise CanonicalDatasetIntegrityError(
                f"canonical Parquet file is missing for {manifest.dataset_version}"
            )
        checksum = _file_checksum(path)
        if checksum != manifest.parquet_checksum_sha256:
            raise CanonicalDatasetIntegrityError(
                f"canonical Parquet checksum mismatch for {manifest.dataset_version}"
            )
        return path


def _ensure_metadata_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_versions (
            dataset_id VARCHAR NOT NULL,
            dataset_version VARCHAR PRIMARY KEY,
            created_at VARCHAR NOT NULL,
            primary_provider_id VARCHAR NOT NULL,
            source_batch_ids_json VARCHAR NOT NULL,
            transformation_version VARCHAR NOT NULL,
            adjustment_policy_version VARCHAR NOT NULL,
            universe_construction_version VARCHAR NOT NULL,
            quality_check_version VARCHAR NOT NULL,
            pass_count BIGINT NOT NULL,
            warn_count BIGINT NOT NULL,
            quarantine_count BIGINT NOT NULL,
            reject_count BIGINT NOT NULL,
            record_count BIGINT NOT NULL,
            first_trade_date DATE NOT NULL,
            last_trade_date DATE NOT NULL,
            content_checksum_sha256 VARCHAR NOT NULL,
            parquet_checksum_sha256 VARCHAR NOT NULL,
            parquet_relative_path VARCHAR NOT NULL
        )
        """
    )


def _quality_summary(bars: tuple[DailyBar, ...]) -> DatasetQualitySummary:
    counts = {status: 0 for status in QualityStatus}
    for bar in bars:
        counts[bar.quality_status] += 1
    return DatasetQualitySummary(
        pass_count=counts[QualityStatus.PASS],
        warn_count=counts[QualityStatus.WARN],
        quarantine_count=counts[QualityStatus.QUARANTINE],
        reject_count=counts[QualityStatus.REJECT],
    )


def _logical_checksum(bars: tuple[DailyBar, ...]) -> str:
    digest = sha256()
    for bar in bars:
        payload = json.dumps(
            _daily_bar_json_row(bar),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(payload)
        digest.update(b"\n")
    return digest.hexdigest()


def _daily_bar_json_row(bar: DailyBar) -> list[object]:
    return [
        str(bar.instrument_id),
        bar.trade_date.isoformat(),
        bar.open_raw,
        bar.high_raw,
        bar.low_raw,
        bar.close_raw,
        bar.volume_raw,
        bar.split_factor,
        bar.dividend_cash,
        bar.open_split_adjusted,
        bar.high_split_adjusted,
        bar.low_split_adjusted,
        bar.close_split_adjusted,
        bar.provider_id,
        str(bar.dataset_version),
        str(bar.quality_status),
    ]


def _daily_bar_row(bar: DailyBar) -> tuple[object, ...]:
    return (
        str(bar.instrument_id),
        bar.trade_date,
        bar.open_raw,
        bar.high_raw,
        bar.low_raw,
        bar.close_raw,
        bar.volume_raw,
        bar.split_factor,
        bar.dividend_cash,
        bar.open_split_adjusted,
        bar.high_split_adjusted,
        bar.low_split_adjusted,
        bar.close_split_adjusted,
        bar.provider_id,
        str(bar.dataset_version),
        str(bar.quality_status),
    )


def _daily_bar_from_row(row: tuple[object, ...]) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(str(row[0])),
        trade_date=_require_date(row[1]),
        open_raw=_require_float(row[2]),
        high_raw=_require_float(row[3]),
        low_raw=_require_float(row[4]),
        close_raw=_require_float(row[5]),
        volume_raw=_require_float(row[6]),
        split_factor=_require_float(row[7]),
        dividend_cash=_require_float(row[8]),
        open_split_adjusted=_optional_float(row[9]),
        high_split_adjusted=_optional_float(row[10]),
        low_split_adjusted=_optional_float(row[11]),
        close_split_adjusted=_optional_float(row[12]),
        provider_id=str(row[13]),
        dataset_version=DatasetVersion(str(row[14])),
        quality_status=QualityStatus(str(row[15])),
    )


def _manifest_from_row(row: tuple[object, ...]) -> CanonicalDatasetManifest:
    source_batch_ids_raw: object = json.loads(str(row[4]))
    if not isinstance(source_batch_ids_raw, list) or not all(
        isinstance(value, str) for value in source_batch_ids_raw
    ):
        raise CanonicalDatasetIntegrityError("dataset manifest contains invalid source_batch_ids")
    source_batch_ids = cast(tuple[str, ...], tuple(source_batch_ids_raw))

    return CanonicalDatasetManifest(
        dataset_id=str(row[0]),
        dataset_version=DatasetVersion(str(row[1])),
        created_at=_require_aware_datetime(str(row[2])),
        primary_provider_id=str(row[3]),
        source_batch_ids=source_batch_ids,
        transformation_version=str(row[5]),
        adjustment_policy_version=str(row[6]),
        universe_construction_version=str(row[7]),
        quality_check_version=str(row[8]),
        quality_summary=DatasetQualitySummary(
            pass_count=_require_int(row[9]),
            warn_count=_require_int(row[10]),
            quarantine_count=_require_int(row[11]),
            reject_count=_require_int(row[12]),
        ),
        record_count=_require_int(row[13]),
        first_trade_date=_require_date(row[14]),
        last_trade_date=_require_date(row[15]),
        content_checksum_sha256=str(row[16]),
        parquet_checksum_sha256=str(row[17]),
        parquet_relative_path=str(row[18]),
    )


def _same_promotion(
    manifest: CanonicalDatasetManifest,
    request: DatasetPromotionRequest,
    content_checksum: str,
) -> bool:
    return (
        manifest.dataset_id == request.dataset_id
        and manifest.dataset_version == request.dataset_version
        and manifest.created_at == request.created_at
        and manifest.primary_provider_id == request.primary_provider_id
        and manifest.source_batch_ids == request.source_batch_ids
        and manifest.transformation_version == request.transformation_version
        and manifest.adjustment_policy_version == request.adjustment_policy_version
        and manifest.universe_construction_version == request.universe_construction_version
        and manifest.quality_check_version == request.quality_check_version
        and manifest.content_checksum_sha256 == content_checksum
    )


def _verify_parquet_row_count(path: Path, *, expected: int) -> None:
    connection = duckdb.connect()
    try:
        row = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(path)})"
        ).fetchone()
    finally:
        connection.close()
    if row is None or _require_int(row[0]) != expected:
        raise CanonicalDatasetIntegrityError(
            f"Parquet row-count verification failed: expected {expected} records"
        )


def _file_checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _validate_version(value: str) -> None:
    if _SAFE_VERSION.fullmatch(value) is None:
        raise ValueError("dataset_version contains unsupported path characters")


def _validate_non_empty(value: str, *, field: str) -> None:
    if not value.strip():
        raise ValueError(f"{field} must be non-empty")


def _validate_aware_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")


def _require_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    _validate_aware_datetime(parsed)
    return parsed


def _require_date(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise CanonicalDatasetIntegrityError("canonical dataset contains an invalid date value")
    return value


def _require_float(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise CanonicalDatasetIntegrityError("canonical dataset contains an invalid numeric value")
    return float(value)


def _require_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CanonicalDatasetIntegrityError("canonical dataset contains an invalid integer value")
    return value


def _optional_float(value: object) -> float | None:
    return None if value is None else _require_float(value)
