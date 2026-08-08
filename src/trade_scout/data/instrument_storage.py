"""Immutable Parquet/DuckDB storage for canonical instrument and symbol-history snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any

import duckdb

from trade_scout.data.contracts import (
    InstrumentId,
    InstrumentRecord,
    SecurityType,
    SymbolHistoryRecord,
)


class InstrumentMasterStorageError(RuntimeError):
    """Base error for immutable instrument-master snapshot storage."""


class InstrumentMasterConflictError(InstrumentMasterStorageError):
    """Raised when an immutable snapshot identity is reused with different content/provenance."""


class InstrumentMasterIntegrityError(InstrumentMasterStorageError):
    """Raised when canonical identity/history content is inconsistent or physically corrupted."""


class InstrumentMasterNotFoundError(InstrumentMasterStorageError):
    """Raised when a requested snapshot version is not registered."""


@dataclass(frozen=True, slots=True)
class InstrumentMasterPromotionRequest:
    """Version/provenance metadata required to promote one identity snapshot."""

    snapshot_version: str
    primary_provider_id: str
    created_at: datetime
    source_batch_ids: tuple[str, ...]
    identity_definition_version: str
    symbol_history_definition_version: str

    def __post_init__(self) -> None:
        for name, value in (
            ("snapshot_version", self.snapshot_version),
            ("primary_provider_id", self.primary_provider_id),
            ("identity_definition_version", self.identity_definition_version),
            ("symbol_history_definition_version", self.symbol_history_definition_version),
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
class InstrumentMasterManifest:
    """Registered immutable identity snapshot and its integrity metadata."""

    snapshot_version: str
    primary_provider_id: str
    created_at: datetime
    source_batch_ids: tuple[str, ...]
    identity_definition_version: str
    symbol_history_definition_version: str
    instrument_count: int
    symbol_history_count: int
    instrument_logical_sha256: str
    symbol_history_logical_sha256: str
    instrument_parquet_sha256: str
    symbol_history_parquet_sha256: str
    instrument_parquet_relative_path: str
    symbol_history_parquet_relative_path: str


@dataclass(frozen=True, slots=True)
class InstrumentMasterSnapshot:
    """Loaded canonical instrument master plus dated symbol history."""

    manifest: InstrumentMasterManifest
    instruments: tuple[InstrumentRecord, ...]
    symbol_history: tuple[SymbolHistoryRecord, ...]


class InstrumentMasterStore:
    """Promote/load immutable canonical identity snapshots using Parquet plus DuckDB metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.metadata_path = root / "metadata" / "datasets.duckdb"

    def promote(
        self,
        instruments: Iterable[InstrumentRecord],
        symbol_history: Iterable[SymbolHistoryRecord],
        request: InstrumentMasterPromotionRequest,
    ) -> InstrumentMasterManifest:
        """Validate and atomically register one immutable instrument-master snapshot."""

        canonical_instruments = tuple(sorted(instruments, key=lambda item: str(item.instrument_id)))
        canonical_history = tuple(
            sorted(
                symbol_history,
                key=lambda item: (
                    str(item.instrument_id),
                    item.effective_from,
                    item.effective_to or date.max,
                    item.symbol,
                    item.exchange,
                ),
            )
        )
        _validate_snapshot(
            canonical_instruments,
            canonical_history,
            primary_provider_id=request.primary_provider_id,
        )

        instrument_payload = [_instrument_payload(item) for item in canonical_instruments]
        history_payload = [_history_payload(item) for item in canonical_history]
        instrument_logical = _logical_checksum(instrument_payload)
        history_logical = _logical_checksum(history_payload)

        existing = self._get_manifest_or_none(request.snapshot_version)
        if existing is not None:
            expected = _manifest_identity(
                request,
                instrument_count=len(canonical_instruments),
                symbol_history_count=len(canonical_history),
                instrument_logical_sha256=instrument_logical,
                symbol_history_logical_sha256=history_logical,
            )
            if _registered_identity(existing) != expected:
                raise InstrumentMasterConflictError(
                    f"snapshot {request.snapshot_version} already exists with different "
                    "content/provenance"
                )
            self._verify_manifest_files(existing)
            return existing

        instrument_relative = (
            Path("canonical")
            / "instrument_master"
            / request.snapshot_version
            / "instruments.parquet"
        )
        history_relative = (
            Path("canonical")
            / "symbol_history"
            / request.snapshot_version
            / "symbol_history.parquet"
        )
        instrument_path = self.root / instrument_relative
        history_path = self.root / history_relative
        if instrument_path.exists() or history_path.exists():
            raise InstrumentMasterConflictError(
                "unregistered canonical identity files already exist for this snapshot version"
            )

        instrument_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            _write_instruments_parquet(instrument_path, canonical_instruments)
            _write_symbol_history_parquet(history_path, canonical_history)
            instrument_physical = _file_sha256(instrument_path)
            history_physical = _file_sha256(history_path)
            manifest = InstrumentMasterManifest(
                snapshot_version=request.snapshot_version,
                primary_provider_id=request.primary_provider_id,
                created_at=request.created_at,
                source_batch_ids=request.source_batch_ids,
                identity_definition_version=request.identity_definition_version,
                symbol_history_definition_version=request.symbol_history_definition_version,
                instrument_count=len(canonical_instruments),
                symbol_history_count=len(canonical_history),
                instrument_logical_sha256=instrument_logical,
                symbol_history_logical_sha256=history_logical,
                instrument_parquet_sha256=instrument_physical,
                symbol_history_parquet_sha256=history_physical,
                instrument_parquet_relative_path=instrument_relative.as_posix(),
                symbol_history_parquet_relative_path=history_relative.as_posix(),
            )
            self._register(manifest)
        except Exception:
            if self._get_manifest_or_none(request.snapshot_version) is None:
                instrument_path.unlink(missing_ok=True)
                history_path.unlink(missing_ok=True)
            raise
        return manifest

    def get_manifest(self, snapshot_version: str) -> InstrumentMasterManifest:
        """Return registered metadata for one snapshot version."""

        manifest = self._get_manifest_or_none(snapshot_version)
        if manifest is None:
            raise InstrumentMasterNotFoundError(f"unknown instrument snapshot {snapshot_version}")
        return manifest

    def load(self, snapshot_version: str) -> InstrumentMasterSnapshot:
        """Load and integrity-check one immutable identity snapshot."""

        manifest = self.get_manifest(snapshot_version)
        self._verify_manifest_files(manifest)
        instruments = _read_instruments(self.root / manifest.instrument_parquet_relative_path)
        history = _read_symbol_history(self.root / manifest.symbol_history_parquet_relative_path)
        _validate_snapshot(instruments, history, primary_provider_id=manifest.primary_provider_id)
        if _logical_checksum([_instrument_payload(item) for item in instruments]) != (
            manifest.instrument_logical_sha256
        ):
            raise InstrumentMasterIntegrityError("instrument logical checksum mismatch")
        if _logical_checksum([_history_payload(item) for item in history]) != (
            manifest.symbol_history_logical_sha256
        ):
            raise InstrumentMasterIntegrityError("symbol-history logical checksum mismatch")
        return InstrumentMasterSnapshot(
            manifest=manifest,
            instruments=instruments,
            symbol_history=history,
        )

    def _register(self, manifest: InstrumentMasterManifest) -> None:
        self._initialize_registry()
        with duckdb.connect(str(self.metadata_path)) as connection:
            connection.execute(
                """
                INSERT INTO instrument_master_versions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    manifest.snapshot_version,
                    manifest.primary_provider_id,
                    manifest.created_at,
                    json.dumps(manifest.source_batch_ids),
                    manifest.identity_definition_version,
                    manifest.symbol_history_definition_version,
                    manifest.instrument_count,
                    manifest.symbol_history_count,
                    manifest.instrument_logical_sha256,
                    manifest.symbol_history_logical_sha256,
                    manifest.instrument_parquet_sha256,
                    manifest.symbol_history_parquet_sha256,
                    manifest.instrument_parquet_relative_path,
                    manifest.symbol_history_parquet_relative_path,
                    datetime.now(manifest.created_at.tzinfo),
                ),
            )

    def _get_manifest_or_none(self, snapshot_version: str) -> InstrumentMasterManifest | None:
        if not self.metadata_path.exists():
            return None
        self._initialize_registry()
        with duckdb.connect(str(self.metadata_path), read_only=True) as connection:
            row = connection.execute(
                """
                SELECT snapshot_version, primary_provider_id, created_at, source_batch_ids,
                       identity_definition_version, symbol_history_definition_version,
                       instrument_count, symbol_history_count, instrument_logical_sha256,
                       symbol_history_logical_sha256, instrument_parquet_sha256,
                       symbol_history_parquet_sha256, instrument_parquet_relative_path,
                       symbol_history_parquet_relative_path
                FROM instrument_master_versions WHERE snapshot_version = ?
                """,
                (snapshot_version,),
            ).fetchone()
        return None if row is None else _manifest_from_row(row)

    def _initialize_registry(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.metadata_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS instrument_master_versions (
                    snapshot_version VARCHAR PRIMARY KEY,
                    primary_provider_id VARCHAR NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    source_batch_ids VARCHAR NOT NULL,
                    identity_definition_version VARCHAR NOT NULL,
                    symbol_history_definition_version VARCHAR NOT NULL,
                    instrument_count BIGINT NOT NULL,
                    symbol_history_count BIGINT NOT NULL,
                    instrument_logical_sha256 VARCHAR NOT NULL,
                    symbol_history_logical_sha256 VARCHAR NOT NULL,
                    instrument_parquet_sha256 VARCHAR NOT NULL,
                    symbol_history_parquet_sha256 VARCHAR NOT NULL,
                    instrument_parquet_relative_path VARCHAR NOT NULL,
                    symbol_history_parquet_relative_path VARCHAR NOT NULL,
                    registered_at TIMESTAMPTZ NOT NULL
                )
                """
            )

    def _verify_manifest_files(self, manifest: InstrumentMasterManifest) -> None:
        instrument_path = self.root / manifest.instrument_parquet_relative_path
        history_path = self.root / manifest.symbol_history_parquet_relative_path
        if not instrument_path.is_file() or not history_path.is_file():
            raise InstrumentMasterIntegrityError("registered instrument-master files are missing")
        if _file_sha256(instrument_path) != manifest.instrument_parquet_sha256:
            raise InstrumentMasterIntegrityError("instrument Parquet checksum mismatch")
        if _file_sha256(history_path) != manifest.symbol_history_parquet_sha256:
            raise InstrumentMasterIntegrityError("symbol-history Parquet checksum mismatch")


def _validate_snapshot(
    instruments: tuple[InstrumentRecord, ...],
    history: tuple[SymbolHistoryRecord, ...],
    *,
    primary_provider_id: str,
) -> None:
    if not instruments:
        raise InstrumentMasterIntegrityError("instrument snapshot must not be empty")
    by_id: dict[InstrumentId, InstrumentRecord] = {}
    provider_identity_owner: dict[tuple[str, str], InstrumentId] = {}
    for instrument in instruments:
        if instrument.instrument_id in by_id:
            raise InstrumentMasterIntegrityError(
                f"duplicate instrument_id {instrument.instrument_id}"
            )
        by_id[instrument.instrument_id] = instrument
        primary_identity = instrument.provider_ids.get(primary_provider_id)
        if primary_identity is None or not primary_identity.strip():
            raise InstrumentMasterIntegrityError(
                f"instrument {instrument.instrument_id} lacks primary-provider identity"
            )
        if (
            instrument.first_trade_date
            and instrument.delisting_date
            and instrument.delisting_date < instrument.first_trade_date
        ):
            raise InstrumentMasterIntegrityError(
                f"instrument {instrument.instrument_id} delists before first trade"
            )
        for provider_id, provider_instrument_id in instrument.provider_ids.items():
            if not provider_id.strip() or not provider_instrument_id.strip():
                raise InstrumentMasterIntegrityError(
                    "provider identity keys/values must be non-empty"
                )
            key = (provider_id, provider_instrument_id)
            existing = provider_identity_owner.get(key)
            if existing is not None and existing != instrument.instrument_id:
                raise InstrumentMasterIntegrityError(
                    f"provider identity {provider_id}:{provider_instrument_id} maps to "
                    "multiple instruments"
                )
            provider_identity_owner[key] = instrument.instrument_id

    by_instrument: dict[InstrumentId, list[SymbolHistoryRecord]] = {}
    for record in history:
        if record.instrument_id not in by_id:
            raise InstrumentMasterIntegrityError(
                f"symbol history references unknown instrument {record.instrument_id}"
            )
        if record.effective_to is not None and record.effective_to < record.effective_from:
            raise InstrumentMasterIntegrityError(
                "symbol-history effective_to precedes effective_from"
            )
        by_instrument.setdefault(record.instrument_id, []).append(record)

    for instrument_id, records in by_instrument.items():
        ordered = sorted(
            records, key=lambda item: (item.effective_from, item.effective_to or date.max)
        )
        for previous, current in pairwise(ordered):
            if previous == current:
                raise InstrumentMasterIntegrityError(
                    f"duplicate symbol-history interval for {instrument_id}"
                )
            if previous.effective_to is None or current.effective_from <= previous.effective_to:
                raise InstrumentMasterIntegrityError(
                    f"overlapping symbol-history intervals for {instrument_id}"
                )


def _write_instruments_parquet(path: Path, instruments: tuple[InstrumentRecord, ...]) -> None:
    with duckdb.connect() as connection:
        connection.execute(
            """
            CREATE TABLE instruments (
                instrument_id VARCHAR, primary_symbol VARCHAR, name VARCHAR, exchange VARCHAR,
                security_type VARCHAR, currency VARCHAR, first_trade_date DATE,
                delisting_date DATE, provider_ids_json VARCHAR
            )
            """
        )
        connection.executemany(
            "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    str(item.instrument_id),
                    item.primary_symbol,
                    item.name,
                    item.exchange,
                    str(item.security_type),
                    item.currency,
                    item.first_trade_date,
                    item.delisting_date,
                    json.dumps(dict(item.provider_ids), sort_keys=True, separators=(",", ":")),
                )
                for item in instruments
            ],
        )
        connection.execute(f"COPY instruments TO {_sql_literal(path)} (FORMAT PARQUET)")


def _write_symbol_history_parquet(path: Path, history: tuple[SymbolHistoryRecord, ...]) -> None:
    with duckdb.connect() as connection:
        connection.execute(
            """
            CREATE TABLE symbol_history (
                instrument_id VARCHAR, symbol VARCHAR, exchange VARCHAR,
                effective_from DATE, effective_to DATE
            )
            """
        )
        if history:
            connection.executemany(
                "INSERT INTO symbol_history VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        str(item.instrument_id),
                        item.symbol,
                        item.exchange,
                        item.effective_from,
                        item.effective_to,
                    )
                    for item in history
                ],
            )
        connection.execute(f"COPY symbol_history TO {_sql_literal(path)} (FORMAT PARQUET)")


def _read_instruments(path: Path) -> tuple[InstrumentRecord, ...]:
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            SELECT instrument_id, primary_symbol, name, exchange, security_type, currency,
                   first_trade_date, delisting_date, provider_ids_json
            FROM read_parquet(?) ORDER BY instrument_id
            """,
            (str(path),),
        ).fetchall()
    result: list[InstrumentRecord] = []
    for row in rows:
        provider_ids = json.loads(str(row[8]))
        if not isinstance(provider_ids, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in provider_ids.items()
        ):
            raise InstrumentMasterIntegrityError("provider_ids_json is invalid")
        result.append(
            InstrumentRecord(
                instrument_id=InstrumentId(str(row[0])),
                primary_symbol=str(row[1]),
                name=str(row[2]),
                exchange=str(row[3]),
                security_type=SecurityType(str(row[4])),
                currency=str(row[5]),
                first_trade_date=_optional_date(row[6]),
                delisting_date=_optional_date(row[7]),
                provider_ids=MappingProxyType(provider_ids),
            )
        )
    return tuple(result)


def _read_symbol_history(path: Path) -> tuple[SymbolHistoryRecord, ...]:
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            SELECT instrument_id, symbol, exchange, effective_from, effective_to
            FROM read_parquet(?)
            ORDER BY instrument_id, effective_from, effective_to NULLS LAST, symbol, exchange
            """,
            (str(path),),
        ).fetchall()
    return tuple(
        SymbolHistoryRecord(
            instrument_id=InstrumentId(str(row[0])),
            symbol=str(row[1]),
            exchange=str(row[2]),
            effective_from=_required_date(row[3]),
            effective_to=_optional_date(row[4]),
        )
        for row in rows
    )


def _instrument_payload(item: InstrumentRecord) -> dict[str, Any]:
    return {
        "instrument_id": str(item.instrument_id),
        "primary_symbol": item.primary_symbol,
        "name": item.name,
        "exchange": item.exchange,
        "security_type": str(item.security_type),
        "currency": item.currency,
        "first_trade_date": item.first_trade_date.isoformat() if item.first_trade_date else None,
        "delisting_date": item.delisting_date.isoformat() if item.delisting_date else None,
        "provider_ids": dict(sorted(item.provider_ids.items())),
    }


def _history_payload(item: SymbolHistoryRecord) -> dict[str, Any]:
    return {
        "instrument_id": str(item.instrument_id),
        "symbol": item.symbol,
        "exchange": item.exchange,
        "effective_from": item.effective_from.isoformat(),
        "effective_to": item.effective_to.isoformat() if item.effective_to else None,
    }


def _manifest_identity(
    request: InstrumentMasterPromotionRequest,
    *,
    instrument_count: int,
    symbol_history_count: int,
    instrument_logical_sha256: str,
    symbol_history_logical_sha256: str,
) -> tuple[object, ...]:
    return (
        request.snapshot_version,
        request.primary_provider_id,
        request.created_at,
        request.source_batch_ids,
        request.identity_definition_version,
        request.symbol_history_definition_version,
        instrument_count,
        symbol_history_count,
        instrument_logical_sha256,
        symbol_history_logical_sha256,
    )


def _registered_identity(manifest: InstrumentMasterManifest) -> tuple[object, ...]:
    return (
        manifest.snapshot_version,
        manifest.primary_provider_id,
        manifest.created_at,
        manifest.source_batch_ids,
        manifest.identity_definition_version,
        manifest.symbol_history_definition_version,
        manifest.instrument_count,
        manifest.symbol_history_count,
        manifest.instrument_logical_sha256,
        manifest.symbol_history_logical_sha256,
    )


def _manifest_from_row(row: tuple[object, ...]) -> InstrumentMasterManifest:
    source_ids = json.loads(str(row[3]))
    if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
        raise InstrumentMasterIntegrityError("registered source_batch_ids are invalid")
    created_at = row[2]
    if not isinstance(created_at, datetime):
        raise InstrumentMasterIntegrityError("registered created_at is invalid")
    return InstrumentMasterManifest(
        snapshot_version=str(row[0]),
        primary_provider_id=str(row[1]),
        created_at=created_at,
        source_batch_ids=tuple(source_ids),
        identity_definition_version=str(row[4]),
        symbol_history_definition_version=str(row[5]),
        instrument_count=_required_int(row[6], "instrument_count"),
        symbol_history_count=_required_int(row[7], "symbol_history_count"),
        instrument_logical_sha256=str(row[8]),
        symbol_history_logical_sha256=str(row[9]),
        instrument_parquet_sha256=str(row[10]),
        symbol_history_parquet_sha256=str(row[11]),
        instrument_parquet_relative_path=str(row[12]),
        symbol_history_parquet_relative_path=str(row[13]),
    )


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
        raise InstrumentMasterIntegrityError(f"registered {field} is invalid")
    return value


def _required_date(value: object) -> date:
    if not isinstance(value, date):
        raise InstrumentMasterIntegrityError("required Parquet date is invalid")
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return _required_date(value)
