"""Compose immutable Tiingo lineage case sets for reviewed identity expansion."""

from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.providers.tiingo_lineage_audit import (
    LineageCase,
    TiingoLineageAuditError,
    load_lineage_cases,
)

_COMPOSITION_SCHEMA = "tiingo-lineage-audit-case-composition-v0.1"


def load_lineage_case_source(path: Path) -> tuple[LineageCase, ...]:
    """Load a full lineage case file or recursively composed immutable case set."""

    payload = _load_object(path)
    if payload.get("schema_version") != _COMPOSITION_SCHEMA:
        return load_lineage_cases(path)

    expected_fields = {"schema_version", "base", "additions"}
    if set(payload) != expected_fields:
        raise TiingoLineageAuditError("lineage composition has missing or unknown fields")
    base_path = _resolved_sibling(path, _required_text(payload.get("base"), "base"))
    additions_path = _resolved_sibling(
        path,
        _required_text(payload.get("additions"), "additions"),
    )
    base = load_lineage_case_source(base_path)
    additions = load_lineage_case_source(additions_path)
    combined = tuple(sorted((*base, *additions), key=lambda item: item.source_symbol))
    symbols = [item.source_symbol for item in combined]
    if len(symbols) != len(set(symbols)):
        raise TiingoLineageAuditError("composed Tiingo lineage cases contain duplicate symbols")
    return combined


def _resolved_sibling(source: Path, name: str) -> Path:
    candidate = (source.parent / name).resolve()
    parent = source.parent.resolve()
    if candidate.parent != parent:
        raise TiingoLineageAuditError("lineage composition may reference sibling config files only")
    if candidate == source.resolve():
        raise TiingoLineageAuditError("lineage composition cannot reference itself")
    return candidate


def _load_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoLineageAuditError(f"cannot read lineage case source: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoLineageAuditError("lineage case source is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TiingoLineageAuditError("lineage case source root must be an object")
    return payload


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoLineageAuditError(f"{field} must be non-empty text")
    return value.strip()


__all__ = ["load_lineage_case_source"]
