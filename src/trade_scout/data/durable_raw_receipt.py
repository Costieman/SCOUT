"""Checksum-verified receipts proving that licensed raw evidence is durably present.

Receipts contain control metadata only. They never embed provider payload values or credentials.
A receipt is valid only while the referenced immutable raw batch can be re-read and its checksum,
request fingerprint, and manifest identity still match.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from trade_scout.data.raw_store import RawBatchManifest, RawBatchRecord, RawBatchStore


class DurableRawReceiptError(RuntimeError):
    """Raised when a durable raw-data receipt is malformed, stale, or unverifiable."""


@dataclass(frozen=True, slots=True)
class DurableRawReceipt:
    """Safe proof that one immutable provider response exists in a durable namespace."""

    schema_version: str
    receipt_id: str
    storage_namespace: str
    provider_id: str
    subject_key: str
    batch_id: str
    endpoint: str
    retrieval_time: datetime
    request_fingerprint_sha256: str
    payload_checksum_sha256: str
    content_length: int
    media_type: str | None
    relative_batch_path: str


def create_durable_raw_receipt(
    record: RawBatchRecord,
    *,
    durable_root: Path,
    storage_namespace: str,
    subject_key: str,
) -> DurableRawReceipt:
    """Verify a stored raw batch and mint a deterministic metadata-only receipt."""

    namespace = _required_text(storage_namespace, "storage_namespace")
    subject = _required_text(subject_key, "subject_key")
    root = durable_root.resolve()
    directory = record.directory.resolve()
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise DurableRawReceiptError("raw batch is outside the declared durable root") from exc

    manifest, payload = RawBatchStore(root).read(directory)
    if manifest != record.manifest:
        raise DurableRawReceiptError("raw batch manifest changed before receipt creation")
    if hashlib.sha256(payload).hexdigest() != manifest.checksum_sha256:
        raise DurableRawReceiptError("raw payload checksum does not match its manifest")

    request_fingerprint = _request_fingerprint(manifest)
    receipt_spec = {
        "storage_namespace": namespace,
        "provider_id": manifest.provider_id,
        "subject_key": subject,
        "batch_id": manifest.batch_id,
        "request_fingerprint_sha256": request_fingerprint,
        "payload_checksum_sha256": manifest.checksum_sha256,
    }
    receipt_id = "raw-receipt-" + _sha256_json(receipt_spec)[:24]
    return DurableRawReceipt(
        schema_version="durable-raw-receipt-v0.1",
        receipt_id=receipt_id,
        storage_namespace=namespace,
        provider_id=manifest.provider_id,
        subject_key=subject,
        batch_id=manifest.batch_id,
        endpoint=manifest.endpoint,
        retrieval_time=manifest.retrieval_time,
        request_fingerprint_sha256=request_fingerprint,
        payload_checksum_sha256=manifest.checksum_sha256,
        content_length=manifest.content_length,
        media_type=manifest.media_type,
        relative_batch_path=relative.as_posix(),
    )


def verify_durable_raw_receipt(
    receipt: DurableRawReceipt,
    *,
    durable_root: Path,
    storage_namespace: str,
) -> RawBatchRecord:
    """Re-read raw evidence and fail closed unless every receipt assertion still holds."""

    if receipt.schema_version != "durable-raw-receipt-v0.1":
        raise DurableRawReceiptError("unsupported durable raw receipt schema")
    namespace = _required_text(storage_namespace, "storage_namespace")
    if receipt.storage_namespace != namespace:
        raise DurableRawReceiptError("receipt belongs to another storage namespace")

    root = durable_root.resolve()
    directory = (root / receipt.relative_batch_path).resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise DurableRawReceiptError("receipt path escapes the durable root") from exc

    manifest, payload = RawBatchStore(root).read(directory)
    _assert_manifest_matches_receipt(manifest, receipt)
    if hashlib.sha256(payload).hexdigest() != receipt.payload_checksum_sha256:
        raise DurableRawReceiptError("durable raw payload checksum no longer matches receipt")
    expected_id = "raw-receipt-" + _sha256_json(
        {
            "storage_namespace": receipt.storage_namespace,
            "provider_id": receipt.provider_id,
            "subject_key": receipt.subject_key,
            "batch_id": receipt.batch_id,
            "request_fingerprint_sha256": receipt.request_fingerprint_sha256,
            "payload_checksum_sha256": receipt.payload_checksum_sha256,
        }
    )[:24]
    if receipt.receipt_id != expected_id:
        raise DurableRawReceiptError("durable raw receipt ID is not deterministic for its content")
    return RawBatchRecord(
        manifest=manifest,
        directory=directory,
        payload_path=directory / "payload.bin",
        manifest_path=directory / "manifest.json",
    )


def persist_durable_raw_receipt(path: Path, receipt: DurableRawReceipt) -> None:
    """Atomically persist a receipt without provider payload values."""

    payload = asdict(receipt)
    payload["retrieval_time"] = receipt.retrieval_time.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_durable_raw_receipt(path: Path) -> DurableRawReceipt:
    """Load one strict v0.1 receipt."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DurableRawReceiptError(f"cannot read durable raw receipt: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DurableRawReceiptError("durable raw receipt is invalid JSON") from exc
    expected = {
        "schema_version",
        "receipt_id",
        "storage_namespace",
        "provider_id",
        "subject_key",
        "batch_id",
        "endpoint",
        "retrieval_time",
        "request_fingerprint_sha256",
        "payload_checksum_sha256",
        "content_length",
        "media_type",
        "relative_batch_path",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise DurableRawReceiptError("durable raw receipt has missing or unknown fields")
    try:
        retrieval_time = datetime.fromisoformat(
            _required_text(payload["retrieval_time"], "retrieval_time")
        )
    except ValueError as exc:
        raise DurableRawReceiptError("durable raw receipt retrieval_time is invalid") from exc
    if retrieval_time.tzinfo is None or retrieval_time.utcoffset() is None:
        raise DurableRawReceiptError("durable raw receipt retrieval_time must be timezone-aware")
    content_length = payload["content_length"]
    if not isinstance(content_length, int) or isinstance(content_length, bool) or content_length < 0:
        raise DurableRawReceiptError("durable raw receipt content_length is invalid")
    media_type = payload["media_type"]
    if media_type is not None and (not isinstance(media_type, str) or not media_type.strip()):
        raise DurableRawReceiptError("durable raw receipt media_type is invalid")
    return DurableRawReceipt(
        schema_version=_required_text(payload["schema_version"], "schema_version"),
        receipt_id=_required_text(payload["receipt_id"], "receipt_id"),
        storage_namespace=_required_text(payload["storage_namespace"], "storage_namespace"),
        provider_id=_required_text(payload["provider_id"], "provider_id"),
        subject_key=_required_text(payload["subject_key"], "subject_key"),
        batch_id=_required_text(payload["batch_id"], "batch_id"),
        endpoint=_required_text(payload["endpoint"], "endpoint"),
        retrieval_time=retrieval_time,
        request_fingerprint_sha256=_required_hash(
            payload["request_fingerprint_sha256"], "request_fingerprint_sha256"
        ),
        payload_checksum_sha256=_required_hash(
            payload["payload_checksum_sha256"], "payload_checksum_sha256"
        ),
        content_length=content_length,
        media_type=media_type.strip() if isinstance(media_type, str) else None,
        relative_batch_path=_required_text(payload["relative_batch_path"], "relative_batch_path"),
    )


def _assert_manifest_matches_receipt(
    manifest: RawBatchManifest,
    receipt: DurableRawReceipt,
) -> None:
    if manifest.provider_id != receipt.provider_id:
        raise DurableRawReceiptError("provider ID does not match durable receipt")
    if manifest.batch_id != receipt.batch_id:
        raise DurableRawReceiptError("batch ID does not match durable receipt")
    if manifest.endpoint != receipt.endpoint:
        raise DurableRawReceiptError("endpoint does not match durable receipt")
    if manifest.retrieval_time != receipt.retrieval_time:
        raise DurableRawReceiptError("retrieval time does not match durable receipt")
    if manifest.checksum_sha256 != receipt.payload_checksum_sha256:
        raise DurableRawReceiptError("manifest checksum does not match durable receipt")
    if manifest.content_length != receipt.content_length:
        raise DurableRawReceiptError("content length does not match durable receipt")
    if manifest.media_type != receipt.media_type:
        raise DurableRawReceiptError("media type does not match durable receipt")
    if _request_fingerprint(manifest) != receipt.request_fingerprint_sha256:
        raise DurableRawReceiptError("request fingerprint does not match durable receipt")


def _request_fingerprint(manifest: RawBatchManifest) -> str:
    return _sha256_json(
        {
            "endpoint": manifest.endpoint,
            "request_parameters": dict(manifest.request_parameters),
        }
    )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DurableRawReceiptError(f"{field} must be non-empty text")
    return value.strip()


def _required_hash(value: object, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DurableRawReceiptError(f"{field} must be a lowercase SHA-256 hex digest")
    return text
