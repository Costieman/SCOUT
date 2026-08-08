"""Immutable raw-batch persistence for provider responses and bulk files."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

type Primitive = str | int | float | bool | None

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SENSITIVE_PARAMETER_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "api_token",
        "authorization",
        "access_token",
        "password",
        "secret",
        "token",
    }
)


class RawBatchConflictError(RuntimeError):
    """Raised when an existing immutable batch ID is reused with different content."""


class RawBatchIntegrityError(RuntimeError):
    """Raised when stored raw bytes no longer match their recorded checksum."""


class SecretParameterError(ValueError):
    """Raised when a request manifest contains a credential-like parameter."""


@dataclass(frozen=True, slots=True)
class RawBatchManifest:
    """Immutable metadata recorded alongside one exact raw payload."""

    batch_id: str
    provider_id: str
    endpoint: str
    retrieval_time: datetime
    request_parameters: Mapping[str, Primitive]
    checksum_sha256: str
    content_length: int
    provider_revision: str | None = None
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class RawBatchRecord:
    """Filesystem locations and manifest for a persisted raw batch."""

    manifest: RawBatchManifest
    directory: Path
    payload_path: Path
    manifest_path: Path


class RawBatchStore:
    """Persist exact raw payloads without overwriting prior ingestion batches."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def persist(
        self,
        payload: bytes,
        *,
        batch_id: str,
        provider_id: str,
        endpoint: str,
        retrieval_time: datetime,
        request_parameters: Mapping[str, Primitive],
        provider_revision: str | None = None,
        media_type: str | None = None,
    ) -> RawBatchRecord:
        """Persist one raw response; identical retries are idempotent, not overwrites."""

        _validate_component(batch_id, field="batch_id")
        _validate_component(provider_id, field="provider_id")
        _validate_endpoint(endpoint)
        _validate_timestamp(retrieval_time)
        sanitized_parameters = _validated_request_parameters(request_parameters)

        manifest = RawBatchManifest(
            batch_id=batch_id,
            provider_id=provider_id,
            endpoint=endpoint,
            retrieval_time=retrieval_time,
            request_parameters=sanitized_parameters,
            checksum_sha256=sha256(payload).hexdigest(),
            content_length=len(payload),
            provider_revision=provider_revision,
            media_type=media_type,
        )
        target = self._batch_directory(manifest)

        if target.exists():
            return self._verify_existing(target, manifest, payload)

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{batch_id}.", dir=target.parent))
        try:
            (temporary / "payload.bin").write_bytes(payload)
            (temporary / "manifest.json").write_text(
                _serialize_manifest(manifest),
                encoding="utf-8",
            )
            try:
                os.rename(temporary, target)
            except OSError:
                if not target.exists():
                    raise
                return self._verify_existing(target, manifest, payload)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

        return _record_from_directory(target, manifest)

    def read(self, batch_directory: Path) -> tuple[RawBatchManifest, bytes]:
        """Read and checksum-verify a previously persisted raw batch."""

        manifest = _deserialize_manifest((batch_directory / "manifest.json").read_text("utf-8"))
        payload = (batch_directory / "payload.bin").read_bytes()
        checksum = sha256(payload).hexdigest()
        if checksum != manifest.checksum_sha256 or len(payload) != manifest.content_length:
            raise RawBatchIntegrityError(
                f"raw batch {manifest.batch_id} failed checksum/content-length verification"
            )
        return manifest, payload

    def _batch_directory(self, manifest: RawBatchManifest) -> Path:
        date_partition = manifest.retrieval_time.date().isoformat()
        return self.root / manifest.provider_id / date_partition / manifest.batch_id

    def _verify_existing(
        self,
        target: Path,
        expected_manifest: RawBatchManifest,
        expected_payload: bytes,
    ) -> RawBatchRecord:
        existing_manifest, existing_payload = self.read(target)
        if (
            _manifest_dict(existing_manifest) != _manifest_dict(expected_manifest)
            or existing_payload != expected_payload
        ):
            raise RawBatchConflictError(
                f"immutable raw batch {expected_manifest.batch_id} already exists "
                "with different content"
            )
        return _record_from_directory(target, existing_manifest)


def _record_from_directory(directory: Path, manifest: RawBatchManifest) -> RawBatchRecord:
    return RawBatchRecord(
        manifest=manifest,
        directory=directory,
        payload_path=directory / "payload.bin",
        manifest_path=directory / "manifest.json",
    )


def _validate_component(value: str, *, field: str) -> None:
    if _SAFE_COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{field} contains unsupported path characters")


def _validate_endpoint(endpoint: str) -> None:
    if not endpoint.strip():
        raise ValueError("endpoint must be non-empty")
    if "?" in endpoint or "#" in endpoint:
        raise ValueError("endpoint must not contain query parameters or fragments")


def _validate_timestamp(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieval_time must be timezone-aware")


def _validated_request_parameters(
    parameters: Mapping[str, Primitive],
) -> Mapping[str, Primitive]:
    copied: dict[str, Primitive] = {}
    for key, value in parameters.items():
        normalized = key.strip().lower().replace("-", "_")
        if normalized in _SENSITIVE_PARAMETER_NAMES or normalized.endswith("_token"):
            raise SecretParameterError(f"request parameter {key!r} must not be persisted")
        copied[key] = value
    return MappingProxyType(copied)


def _serialize_manifest(manifest: RawBatchManifest) -> str:
    return json.dumps(_manifest_dict(manifest), sort_keys=True, separators=(",", ":")) + "\n"


def _manifest_dict(manifest: RawBatchManifest) -> dict[str, object]:
    return {
        "batch_id": manifest.batch_id,
        "provider_id": manifest.provider_id,
        "endpoint": manifest.endpoint,
        "retrieval_time": manifest.retrieval_time.isoformat(),
        "request_parameters": dict(manifest.request_parameters),
        "checksum_sha256": manifest.checksum_sha256,
        "content_length": manifest.content_length,
        "provider_revision": manifest.provider_revision,
        "media_type": manifest.media_type,
    }


def _deserialize_manifest(value: str) -> RawBatchManifest:
    raw: object = json.loads(value)
    if not isinstance(raw, dict):
        raise RawBatchIntegrityError("raw batch manifest must be a JSON object")

    return RawBatchManifest(
        batch_id=_require_str(raw, "batch_id"),
        provider_id=_require_str(raw, "provider_id"),
        endpoint=_require_str(raw, "endpoint"),
        retrieval_time=datetime.fromisoformat(_require_str(raw, "retrieval_time")),
        request_parameters=_require_primitive_mapping(raw, "request_parameters"),
        checksum_sha256=_require_str(raw, "checksum_sha256"),
        content_length=_require_int(raw, "content_length"),
        provider_revision=_optional_str(raw, "provider_revision"),
        media_type=_optional_str(raw, "media_type"),
    )


def _require_str(raw: dict[object, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise RawBatchIntegrityError(f"raw batch manifest {key} must be a string")
    return value


def _require_int(raw: dict[object, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RawBatchIntegrityError(f"raw batch manifest {key} must be an integer")
    return value


def _optional_str(raw: dict[object, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RawBatchIntegrityError(f"raw batch manifest {key} must be a string or null")
    return value


def _require_primitive_mapping(
    raw: dict[object, object],
    key: str,
) -> Mapping[str, Primitive]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise RawBatchIntegrityError(f"raw batch manifest {key} must be an object")

    result: dict[str, Primitive] = {}
    for parameter_name, parameter_value in value.items():
        if not isinstance(parameter_name, str) or not _is_primitive(parameter_value):
            raise RawBatchIntegrityError("raw batch manifest contains invalid request parameters")
        result[parameter_name] = parameter_value
    return MappingProxyType(result)


def _is_primitive(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)
