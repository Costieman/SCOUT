"""Validate bounded Tiingo research targets against an already-validated universe snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class TiingoResearchTargetError(RuntimeError):
    """Raised when a bounded research target is malformed or leaves its source universe."""


@dataclass(frozen=True, slots=True)
class TiingoResearchTarget:
    """One versioned acquisition target nested inside a validated source universe."""

    target_version: str
    source_universe_plan: str
    symbols: tuple[str, ...]


def load_tiingo_research_target(
    path: Path,
    *,
    expected_plan_version: str,
    snapshot_symbols: tuple[str, ...],
) -> TiingoResearchTarget:
    """Load a target only when every symbol belongs to the validated source snapshot."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoResearchTargetError(f"cannot read target config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoResearchTargetError("target config is invalid JSON") from exc

    required = {
        "schema_version",
        "target_version",
        "source_universe_plan",
        "purpose",
        "target_count",
        "symbols",
        "selection_notes",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise TiingoResearchTargetError("target config has missing or unknown fields")
    if payload["schema_version"] != "tiingo-research-targets-v0.1":
        raise TiingoResearchTargetError("unsupported target config schema")
    if payload["source_universe_plan"] != expected_plan_version:
        raise TiingoResearchTargetError("target config belongs to another Tiingo universe plan")

    raw_symbols = payload["symbols"]
    if not isinstance(raw_symbols, list) or not all(isinstance(item, str) for item in raw_symbols):
        raise TiingoResearchTargetError("target config symbols must be a list of strings")
    symbols = tuple(item.strip().upper() for item in raw_symbols)
    if not symbols or any(not item for item in symbols) or len(set(symbols)) != len(symbols):
        raise TiingoResearchTargetError("target config symbols must be unique non-empty values")
    if payload["target_count"] != len(symbols):
        raise TiingoResearchTargetError("target config target_count does not match symbols")

    unknown = sorted(set(symbols) - set(snapshot_symbols))
    if unknown:
        raise TiingoResearchTargetError(
            f"target config includes symbols outside the validated snapshot: {unknown}"
        )
    return TiingoResearchTarget(
        target_version=str(payload["target_version"]),
        source_universe_plan=str(payload["source_universe_plan"]),
        symbols=symbols,
    )


__all__ = [
    "TiingoResearchTarget",
    "TiingoResearchTargetError",
    "load_tiingo_research_target",
]
