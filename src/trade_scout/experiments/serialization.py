"""Canonical serialization and hashing for experiment provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from trade_scout.experiments.contracts import JSONValue, ensure_json_value


def to_json_value(value: Any) -> JSONValue:
    """Convert supported experiment objects into canonical JSON-compatible values."""

    if is_dataclass(value) and not isinstance(value, type):
        return to_json_value(asdict(value))
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("manifest/configuration mapping keys must be strings")
            result[key] = to_json_value(item)
        return result
    if isinstance(value, list | tuple):
        return [to_json_value(item) for item in value]
    return ensure_json_value(value)


def canonical_json(value: Any) -> str:
    """Serialize a supported value deterministically for checksums and persistence."""

    return json.dumps(
        to_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    """Return a SHA-256 checksum over canonical JSON representation."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
