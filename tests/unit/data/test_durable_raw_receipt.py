from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.data.durable_raw_receipt import (
    DurableRawReceiptError,
    create_durable_raw_receipt,
    load_durable_raw_receipt,
    persist_durable_raw_receipt,
    verify_durable_raw_receipt,
)
from trade_scout.data.raw_store import RawBatchIntegrityError, RawBatchStore


def _record(root: Path):
    return RawBatchStore(root).persist(
        b'{"prices":[1,2,3]}',
        batch_id="tiingo-example",
        provider_id="tiingo",
        endpoint="/tiingo/daily/AAPL/prices",
        retrieval_time=datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        request_parameters={"startDate": "1996-01-02", "endDate": "2026-08-07"},
        media_type="application/json",
    )


def test_receipt_round_trip_reverifies_raw_payload(tmp_path: Path) -> None:
    raw_root = tmp_path / "durable"
    record = _record(raw_root)
    receipt = create_durable_raw_receipt(
        record,
        durable_root=raw_root,
        storage_namespace="trade-scout-private-raw-v1",
        subject_key="AAPL",
    )
    receipt_path = tmp_path / "receipt.json"
    persist_durable_raw_receipt(receipt_path, receipt)

    loaded = load_durable_raw_receipt(receipt_path)
    verified = verify_durable_raw_receipt(
        loaded,
        durable_root=raw_root,
        storage_namespace="trade-scout-private-raw-v1",
    )

    assert verified.manifest.batch_id == "tiingo-example"
    assert loaded.subject_key == "AAPL"
    assert loaded.payload_checksum_sha256 == record.manifest.checksum_sha256


def test_receipt_rejects_wrong_storage_namespace(tmp_path: Path) -> None:
    raw_root = tmp_path / "durable"
    receipt = create_durable_raw_receipt(
        _record(raw_root),
        durable_root=raw_root,
        storage_namespace="namespace-a",
        subject_key="AAPL",
    )

    with pytest.raises(DurableRawReceiptError, match="another storage namespace"):
        verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace="namespace-b",
        )


def test_receipt_rejects_payload_tampering(tmp_path: Path) -> None:
    raw_root = tmp_path / "durable"
    record = _record(raw_root)
    receipt = create_durable_raw_receipt(
        record,
        durable_root=raw_root,
        storage_namespace="trade-scout-private-raw-v1",
        subject_key="AAPL",
    )
    record.payload_path.write_bytes(b"tampered")

    with pytest.raises(RawBatchIntegrityError):
        verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace="trade-scout-private-raw-v1",
        )


def test_receipt_cannot_be_created_for_raw_batch_outside_root(tmp_path: Path) -> None:
    record = _record(tmp_path / "actual")

    with pytest.raises(DurableRawReceiptError, match="outside the declared durable root"):
        create_durable_raw_receipt(
            record,
            durable_root=tmp_path / "other",
            storage_namespace="trade-scout-private-raw-v1",
            subject_key="AAPL",
        )
