"""Checkpoint state for resumable historical OHLCV evidence collection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from trade_scout.data.historical_evidence import HistoricalEvidenceCase, HistoricalEvidenceCaseResult

_RUNTIME_ID = "historical-ohlcv-runtime-v0.1"


def case_configuration_id(cases: tuple[HistoricalEvidenceCase, ...]) -> str:
    """Return a stable hash of the ordered evidence-case configuration."""

    payload = [
        {
            "case_id": case.case_id,
            "provider_symbol": case.provider_symbol,
            "start": case.start.isoformat(),
            "end": case.end.isoformat(),
            "minimum_observations": case.minimum_observations,
            "max_start_lag_days": case.max_start_lag_days,
            "max_end_lag_days": case.max_end_lag_days,
        }
        for case in cases
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def new_checkpoint(cases: tuple[HistoricalEvidenceCase, ...]) -> dict[str, Any]:
    """Create empty checkpoint state tied to one exact case configuration."""

    return {
        "runtime_id": _RUNTIME_ID,
        "configuration_id": case_configuration_id(cases),
        "completed_cases": {},
        "last_failure": None,
    }


def load_checkpoint(path: Path, cases: tuple[HistoricalEvidenceCase, ...]) -> dict[str, Any]:
    """Load compatible checkpoint state or create a new checkpoint when none exists."""

    if not path.exists():
        return new_checkpoint(cases)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read historical evidence checkpoint: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"historical evidence checkpoint is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("historical evidence checkpoint root must be an object")
    if payload.get("runtime_id") != _RUNTIME_ID:
        raise ValueError("historical evidence checkpoint runtime_id is incompatible")
    expected = case_configuration_id(cases)
    if payload.get("configuration_id") != expected:
        raise ValueError(
            "historical evidence checkpoint configuration does not match requested cases"
        )
    completed = payload.get("completed_cases")
    if not isinstance(completed, dict):
        raise ValueError("historical evidence checkpoint completed_cases must be an object")
    payload.setdefault("last_failure", None)
    return payload


def record_completed_case(
    checkpoint: dict[str, Any],
    result: HistoricalEvidenceCaseResult,
) -> None:
    """Persist one completed case result into in-memory checkpoint state."""

    completed = checkpoint.get("completed_cases")
    if not isinstance(completed, dict):
        raise ValueError("historical evidence checkpoint completed_cases must be an object")
    completed[result.case_id] = asdict(result)
    checkpoint["last_failure"] = None


def record_failure(checkpoint: dict[str, Any], *, case_id: str, error: Exception) -> None:
    """Record the most recent provider failure without changing completed evidence."""

    checkpoint["last_failure"] = {
        "case_id": case_id,
        "error_type": type(error).__name__,
        "error": str(error),
    }


def write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    """Atomically replace the checkpoint file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
