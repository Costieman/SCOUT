"""Characterize captured Alpha Vantage responses without inferring undocumented causes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class AlphaVantageResponseClass(StrEnum):
    """Observed response classes derived only from captured bytes and manifest metadata."""

    CSV = "CSV"
    EMPTY_JSON = "EMPTY_JSON"
    API_MESSAGE_JSON = "API_MESSAGE_JSON"
    UNKNOWN_JSON = "UNKNOWN_JSON"
    INVALID_JSON = "INVALID_JSON"


@dataclass(frozen=True, slots=True)
class AlphaVantageCapturedResponse:
    """One immutable captured response and its conservative classification."""

    batch_id: str
    retrieval_time: str
    request_parameters: dict[str, object]
    media_type: str
    content_length: int
    response_class: AlphaVantageResponseClass
    message_key: str | None = None
    message: str | None = None


def characterize_raw_root(raw_root: Path) -> tuple[AlphaVantageCapturedResponse, ...]:
    """Read Alpha Vantage raw-zone batches and classify each captured response."""

    responses: list[AlphaVantageCapturedResponse] = []
    for manifest_path in sorted(raw_root.rglob("manifest.json")):
        payload_path = manifest_path.with_name("payload.bin")
        if not payload_path.exists():
            continue
        manifest = _read_manifest(manifest_path)
        payload = payload_path.read_bytes()
        response_class, message_key, message = _classify(payload)
        request_parameters = manifest.get("request_parameters")
        if not isinstance(request_parameters, dict):
            request_parameters = {}
        responses.append(
            AlphaVantageCapturedResponse(
                batch_id=str(manifest.get("batch_id", manifest_path.parent.name)),
                retrieval_time=str(manifest.get("retrieval_time", "")),
                request_parameters={str(k): v for k, v in request_parameters.items()},
                media_type=str(manifest.get("media_type", "")),
                content_length=len(payload),
                response_class=response_class,
                message_key=message_key,
                message=message,
            )
        )
    return tuple(sorted(responses, key=lambda item: (item.retrieval_time, item.batch_id)))


def summarize_characterization(
    responses: tuple[AlphaVantageCapturedResponse, ...],
) -> dict[str, object]:
    """Produce a machine-readable summary without labeling undocumented provider causes."""

    counts = {item.value: 0 for item in AlphaVantageResponseClass}
    failures: list[dict[str, object]] = []
    for response in responses:
        counts[response.response_class.value] += 1
        if response.response_class is not AlphaVantageResponseClass.CSV:
            failures.append(
                {
                    "batch_id": response.batch_id,
                    "retrieval_time": response.retrieval_time,
                    "request_parameters": response.request_parameters,
                    "response_class": response.response_class.value,
                    "content_length": response.content_length,
                    "message_key": response.message_key,
                    "message": response.message,
                }
            )
    return {
        "response_count": len(responses),
        "class_counts": counts,
        "non_csv_responses": failures,
        "interpretation": (
            "EMPTY_JSON and UNKNOWN_JSON are observed provider responses only; they must not be "
            "relabelled as rate limiting, entitlement failure, or another cause without explicit "
            "provider evidence."
        ),
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Alpha Vantage raw manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Alpha Vantage raw manifest root must be an object: {path}")
    return value


def _classify(payload: bytes) -> tuple[AlphaVantageResponseClass, str | None, str | None]:
    if not payload.lstrip().startswith(b"{"):
        return AlphaVantageResponseClass.CSV, None, None
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return AlphaVantageResponseClass.INVALID_JSON, None, None
    if parsed == {}:
        return AlphaVantageResponseClass.EMPTY_JSON, None, None
    if not isinstance(parsed, dict):
        return AlphaVantageResponseClass.UNKNOWN_JSON, None, None
    for key in ("Error Message", "Information", "Note"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return AlphaVantageResponseClass.API_MESSAGE_JSON, key, value.strip()
    return AlphaVantageResponseClass.UNKNOWN_JSON, None, None
