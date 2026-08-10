"""Tiingo raw-response capture that exposes persisted batch records for receipt minting."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from trade_scout.data.raw_store import Primitive, RawBatchRecord, RawBatchStore


class TiingoReceiptTrackingCapture:
    """Persist exact Tiingo bytes and retain only resulting raw-store record handles."""

    def __init__(self, store: RawBatchStore) -> None:
        self._store = store
        self._records: list[RawBatchRecord] = []

    @property
    def captured_records(self) -> tuple[RawBatchRecord, ...]:
        return tuple(self._records)

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None:
        record = self._store.persist(
            payload,
            batch_id=f"tiingo-{uuid4().hex}",
            provider_id="tiingo",
            endpoint=endpoint,
            retrieval_time=datetime.now(UTC),
            request_parameters=request_parameters,
            media_type="application/json",
        )
        self._records.append(record)
