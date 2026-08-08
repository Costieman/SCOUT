from datetime import UTC, datetime
from pathlib import Path

import pytest

from trade_scout.data.raw_store import (
    RawBatchConflictError,
    RawBatchIntegrityError,
    RawBatchStore,
    SecretParameterError,
)


def _persist(store: RawBatchStore, *, batch_id: str = "batch-001", payload: bytes = b"raw"):
    return store.persist(
        payload,
        batch_id=batch_id,
        provider_id="provider-a",
        endpoint="daily-bars",
        retrieval_time=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        request_parameters={"symbol": "AAA", "start": "2026-08-01"},
        provider_revision="rev-1",
        media_type="application/json",
    )


def test_persist_preserves_exact_payload_and_manifest(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)

    record = _persist(store, payload=b'{"close":123.45}')
    manifest, payload = store.read(record.directory)

    assert payload == b'{"close":123.45}'
    assert manifest.batch_id == "batch-001"
    assert manifest.provider_id == "provider-a"
    assert manifest.request_parameters == {"symbol": "AAA", "start": "2026-08-01"}
    assert len(manifest.checksum_sha256) == 64
    assert record.payload_path.read_bytes() == payload


def test_identical_retry_is_idempotent(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)

    first = _persist(store)
    second = _persist(store)

    assert second.directory == first.directory
    assert second.manifest == first.manifest
    assert len(list((tmp_path / "provider-a" / "2026-08-08").iterdir())) == 1


def test_batch_id_cannot_be_reused_for_different_payload(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)
    _persist(store, payload=b"first")

    with pytest.raises(RawBatchConflictError):
        _persist(store, payload=b"corrected")


def test_vendor_correction_uses_new_batch_without_overwriting_prior_raw(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)

    first = _persist(store, batch_id="batch-001", payload=b"original")
    corrected = _persist(store, batch_id="batch-002", payload=b"corrected")

    assert first.payload_path.read_bytes() == b"original"
    assert corrected.payload_path.read_bytes() == b"corrected"
    assert first.directory != corrected.directory


def test_credential_like_request_parameter_is_rejected(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)

    with pytest.raises(SecretParameterError):
        store.persist(
            b"raw",
            batch_id="batch-001",
            provider_id="provider-a",
            endpoint="daily-bars",
            retrieval_time=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            request_parameters={"api_key": "must-not-be-written"},
        )

    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_read_detects_payload_tampering(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)
    record = _persist(store, payload=b"original")
    record.payload_path.write_bytes(b"tampered")

    with pytest.raises(RawBatchIntegrityError):
        store.read(record.directory)


def test_retrieval_timestamp_must_be_timezone_aware(tmp_path: Path) -> None:
    store = RawBatchStore(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        store.persist(
            b"raw",
            batch_id="batch-001",
            provider_id="provider-a",
            endpoint="daily-bars",
            retrieval_time=datetime(2026, 8, 8, 12, 0),
            request_parameters={},
        )
