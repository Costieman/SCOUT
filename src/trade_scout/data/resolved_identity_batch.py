"""Assemble independently proven deferred Tiingo identity evidence for batch promotion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.auto_identity_import import AutoIdentityEvidence


class ResolvedIdentityBatchError(RuntimeError):
    """Raised when resolved identity evidence cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class ResolvedIdentityBatch:
    evidence: tuple[AutoIdentityEvidence, ...]
    deferred_resolver_count: int
    historical_index_count: int
    extended_resolver_count: int = 0


def load_resolved_identity_batch(
    *,
    deferred_ready_path: Path,
    deferred_remaining_path: Path,
    historical_ready_path: Path,
    extended_ready_path: Path | None = None,
) -> ResolvedIdentityBatch:
    """Load and reconcile READY evidence from all fail-closed resolver layers."""

    deferred_ready = _load_json(deferred_ready_path)
    historical_ready = _load_json(historical_ready_path)
    remaining = _load_json(deferred_remaining_path)
    deferred_rows = _list(deferred_ready, "resolutions", deferred_ready_path)
    historical_rows = _list(historical_ready, "evidence", historical_ready_path)
    remaining_rows = _list(remaining, "resolutions", deferred_remaining_path)
    extended_rows: list[dict[str, object]] = []
    if extended_ready_path is not None and extended_ready_path.is_file():
        extended_rows = _list(_load_json(extended_ready_path), "resolutions", extended_ready_path)

    context: dict[str, dict[str, object]] = {}
    for row in remaining_rows:
        source = _text(row.get("source_symbol"), "remaining source_symbol").upper()
        for key in _symbol_aliases(source):
            previous = context.get(key)
            if previous is not None and previous is not row:
                raise ResolvedIdentityBatchError(f"ambiguous deferred context for symbol alias {key}")
            context[key] = row

    assembled: list[AutoIdentityEvidence] = []
    for row in deferred_rows:
        assembled.append(_evidence_from_resolution(row, "deferred"))

    historical_count = 0
    for row in historical_rows:
        if _text(row.get("status"), "historical status").upper() != "READY":
            raise ResolvedIdentityBatchError("historical ready file contains a non-READY row")
        historical_symbol = _text(row.get("symbol"), "historical symbol").upper()
        matches = {
            id(context[key]): context[key]
            for key in _symbol_aliases(historical_symbol)
            if key in context
        }
        if len(matches) != 1:
            raise ResolvedIdentityBatchError(
                f"historical READY {historical_symbol} does not map uniquely to deferred context"
            )
        assembled.append(_evidence_from_historical(row, next(iter(matches.values()))))
        historical_count += 1

    for row in extended_rows:
        assembled.append(_evidence_from_resolution(row, "extended"))

    by_symbol: dict[str, AutoIdentityEvidence] = {}
    for item in assembled:
        symbol = item.source_symbol.upper()
        if symbol in by_symbol:
            raise ResolvedIdentityBatchError(f"duplicate READY evidence for {symbol}")
        by_symbol[symbol] = item

    return ResolvedIdentityBatch(
        evidence=tuple(by_symbol[symbol] for symbol in sorted(by_symbol)),
        deferred_resolver_count=len(deferred_rows),
        historical_index_count=historical_count,
        extended_resolver_count=len(extended_rows),
    )


def _evidence_from_resolution(row: dict[str, object], source: str) -> AutoIdentityEvidence:
    if _text(row.get("status"), f"{source} status").upper() != "READY":
        raise ResolvedIdentityBatchError(f"{source} ready file contains a non-READY row")
    return AutoIdentityEvidence(
        source_symbol=_text(row.get("source_symbol"), f"{source} source_symbol").upper(),
        observed_first_date=_iso_date(row.get("observed_first_date"), "observed_first_date"),
        cik=_required_int(row.get("cik"), f"{source} cik"),
        company_name=_text(row.get("company_name"), f"{source} company_name"),
        exchange=_text(row.get("exchange"), f"{source} exchange"),
        source_url=_text(row.get("evidence_url"), f"{source} evidence_url"),
        source_title=_optional_text(row.get("evidence_title")),
        evidence_kind=_text(row.get("resolution_kind"), f"{source} resolution_kind"),
        ready=True,
        reason=_text(row.get("reason"), f"{source} reason"),
    )


def _evidence_from_historical(
    historical: dict[str, object], source_row: dict[str, object]
) -> AutoIdentityEvidence:
    historical_cik = _required_int(historical.get("cik"), "historical cik")
    source_cik = _required_int(source_row.get("cik"), "source cik")
    if historical_cik != source_cik:
        raise ResolvedIdentityBatchError("historical READY CIK differs from the deferred-resolution CIK")
    source_symbol = _text(source_row.get("source_symbol"), "source_symbol").upper()
    historical_symbol = _text(historical.get("symbol"), "historical symbol").upper()
    if not set(_symbol_aliases(source_symbol)).intersection(_symbol_aliases(historical_symbol)):
        raise ResolvedIdentityBatchError(
            f"historical ticker {historical_symbol} does not match source symbol {source_symbol}"
        )
    return AutoIdentityEvidence(
        source_symbol=source_symbol,
        observed_first_date=_iso_date(source_row.get("observed_first_date"), "observed_first_date"),
        cik=historical_cik,
        company_name=_text(source_row.get("company_name"), "company_name"),
        exchange=_text(source_row.get("exchange"), "exchange"),
        source_url=_text(historical.get("pre_boundary_url"), "pre_boundary_url"),
        source_title="SEC EDGAR historical full-index pre-boundary filing",
        evidence_kind=_text(historical.get("kind"), "historical kind"),
        ready=True,
        reason=_text(historical.get("reason"), "historical reason"),
    )


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ResolvedIdentityBatchError(f"required evidence file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResolvedIdentityBatchError(f"evidence file must contain an object: {path}")
    return payload


def _list(payload: dict[str, object], field: str, path: Path) -> list[dict[str, object]]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ResolvedIdentityBatchError(f"{path} is missing list field {field}")
    result: list[dict[str, object]] = []
    for row in value:
        if not isinstance(row, dict):
            raise ResolvedIdentityBatchError(f"{path} contains malformed {field} row")
        result.append(row)
    return result


def _symbol_aliases(value: str) -> tuple[str, ...]:
    symbol = value.strip().upper()
    aliases = {symbol}
    if "." in symbol:
        aliases.add(symbol.replace(".", "-"))
    if "-" in symbol:
        aliases.add(symbol.replace("-", "."))
    return tuple(sorted(aliases))


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResolvedIdentityBatchError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _required_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ResolvedIdentityBatchError(f"{field} must be a positive integer")
    return value


def _iso_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError as exc:
        raise ResolvedIdentityBatchError(f"{field} must be an ISO date") from exc


__all__ = ["ResolvedIdentityBatch", "ResolvedIdentityBatchError", "load_resolved_identity_batch"]
