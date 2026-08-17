"""Scoped read-only access to immutable canonical daily-bar Parquet datasets.

This serving helper complements ``CanonicalDailyBarStore.load`` for interactive research. It keeps
full-file integrity verification, but reads only the reviewed instruments and trading-day window
needed by a request. The verified file signature is cached in-process and is invalidated if size or
mtime changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from pathlib import Path

import duckdb

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetIntegrityError,
    CanonicalDatasetNotFoundError,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


@dataclass(slots=True)
class CanonicalDailyBarWindowReader:
    """Read exact instrument/date windows from one registered immutable canonical dataset."""

    root: Path
    dataset_version: DatasetVersion
    _verified_signature: tuple[int, int, str] | None = field(default=None, init=False, repr=False)

    def manifest_record_count(self) -> int:
        return self._manifest().record_count

    def latest_trade_date(self) -> date:
        return self._manifest().last_trade_date

    def load_window(
        self,
        *,
        instrument_ids: tuple[str, ...],
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        """Return rows through ``signal_end`` plus exact pre-window warm-up per instrument."""

        if signal_end < signal_start:
            raise ValueError("signal_end must be on or after signal_start")
        if warmup_observations < 0:
            raise ValueError("warmup_observations must be non-negative")
        reviewed = tuple(dict.fromkeys(value.strip() for value in instrument_ids if value.strip()))
        if not reviewed:
            raise ValueError("at least one instrument_id is required for a canonical window")

        parquet_path = self._verified_parquet_path()
        connection = duckdb.connect()
        try:
            connection.execute(
                "CREATE TEMP TABLE selected_instruments (instrument_id VARCHAR PRIMARY KEY)"
            )
            connection.executemany(
                "INSERT INTO selected_instruments VALUES (?)",
                [(value,) for value in reviewed],
            )
            rows = connection.execute(
                f"""
                WITH scoped AS (
                    SELECT
                        p.instrument_id,
                        p.trade_date,
                        p.open_raw,
                        p.high_raw,
                        p.low_raw,
                        p.close_raw,
                        p.volume_raw,
                        p.split_factor,
                        p.dividend_cash,
                        p.open_split_adjusted,
                        p.high_split_adjusted,
                        p.low_split_adjusted,
                        p.close_split_adjusted,
                        p.provider_id,
                        p.dataset_version,
                        p.quality_status,
                        CASE
                            WHEN p.trade_date < ? THEN
                                ROW_NUMBER() OVER (
                                    PARTITION BY p.instrument_id, (p.trade_date < ?)
                                    ORDER BY p.trade_date DESC, p.provider_id DESC
                                )
                            ELSE NULL
                        END AS warmup_rank
                    FROM read_parquet({_sql_literal(parquet_path)}) AS p
                    INNER JOIN selected_instruments AS s USING (instrument_id)
                    WHERE p.trade_date <= ?
                )
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
                FROM scoped
                WHERE trade_date >= ? OR warmup_rank <= ?
                ORDER BY instrument_id, trade_date, provider_id
                """,
                [
                    signal_start,
                    signal_start,
                    signal_end,
                    signal_start,
                    warmup_observations,
                ],
            ).fetchall()
        finally:
            connection.close()
        return tuple(_daily_bar_from_row(row) for row in rows)

    def _manifest(self):
        manifest = CanonicalDailyBarStore(self.root).get_manifest(self.dataset_version)
        if manifest is None:
            raise CanonicalDatasetNotFoundError(str(self.dataset_version))
        return manifest

    def _verified_parquet_path(self) -> Path:
        manifest = self._manifest()
        path = self.root / manifest.parquet_relative_path
        if not path.is_file():
            raise CanonicalDatasetIntegrityError(
                f"canonical Parquet file is missing for {manifest.dataset_version}"
            )
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns, manifest.parquet_checksum_sha256)
        if self._verified_signature == signature:
            return path
        if _file_checksum(path) != manifest.parquet_checksum_sha256:
            raise CanonicalDatasetIntegrityError(
                f"canonical Parquet checksum mismatch for {manifest.dataset_version}"
            )
        self._verified_signature = signature
        return path


def _daily_bar_from_row(row: tuple[object, ...]) -> DailyBar:
    trade_date = row[1]
    if not isinstance(trade_date, date):
        raise CanonicalDatasetIntegrityError("canonical window returned an invalid trade_date")
    return DailyBar(
        instrument_id=InstrumentId(str(row[0])),
        trade_date=trade_date,
        open_raw=float(row[2]),
        high_raw=float(row[3]),
        low_raw=float(row[4]),
        close_raw=float(row[5]),
        volume_raw=float(row[6]),
        split_factor=float(row[7]),
        dividend_cash=float(row[8]),
        open_split_adjusted=_optional_float(row[9]),
        high_split_adjusted=_optional_float(row[10]),
        low_split_adjusted=_optional_float(row[11]),
        close_split_adjusted=_optional_float(row[12]),
        provider_id=str(row[13]),
        dataset_version=DatasetVersion(str(row[14])),
        quality_status=QualityStatus(str(row[15])),
    )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _file_checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


__all__ = ["CanonicalDailyBarWindowReader"]
