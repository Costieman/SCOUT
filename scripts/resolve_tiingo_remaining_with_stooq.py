"""Probe only unresolved Tiingo boundary cases with bounded Stooq evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest, ProviderDailyBar
from trade_scout.data.providers.stooq import (
    StooqAdapter,
    StooqApiError,
    StooqInstrumentLink,
    StooqResponseError,
)
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.data.stooq_boundary_evidence import classify_stooq_boundary_evidence


class RemainingStooqResolutionError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    reviewed_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    remaining_path = root / "evidence" / "deferred-resolution" / "extended" / "remaining.json"
    output_root = root / "evidence" / "deferred-resolution" / "stooq-boundary"
    raw_root = output_root / "raw"
    checkpoint_path = output_root / "checkpoint.json"
    summary_path = output_root / "summary.json"

    try:
        locked = _locked_symbols(reviewed_path)
        rows = _eligible_rows(remaining_path, locked)
        completed = _load_checkpoint(checkpoint_path)

        links = tuple(
            StooqInstrumentLink(
                query_symbol=query_symbol,
                provider_instrument_id=f"stooq-boundary-evidence:{symbol}:{query_symbol}",
            )
            for symbol in sorted(rows)
            for query_symbol in _stooq_query_candidates(symbol)
        )
        adapter = StooqAdapter.from_http(instrument_links=links, raw_root=raw_root)

        for index, symbol in enumerate(sorted(rows), start=1):
            if symbol in completed:
                print(f"[{index}/{len(rows)}] {symbol}: SKIPPED checkpoint", flush=True)
                continue
            boundary = date.fromisoformat(_text(rows[symbol].get("observed_first_date")))
            start = boundary - timedelta(days=45)
            end = boundary + timedelta(days=15)
            print(f"[{index}/{len(rows)}] {symbol}: Stooq boundary evidence", flush=True)
            try:
                bars, query_symbol = _fetch_stooq_bars(
                    adapter=adapter,
                    symbol=symbol,
                    start=start,
                    end=end,
                    boundary=boundary,
                )
            except StooqApiError as exc:
                _write(
                    checkpoint_path,
                    {
                        "schema_version": "tiingo-stooq-boundary-checkpoint-v0.1",
                        "completed": completed,
                        "last_failure": {"symbol": symbol, "error": str(exc)},
                    },
                )
                print(f"    -> PAUSED {exc}", file=sys.stderr, flush=True)
                return 2

            if bars is None:
                completed[symbol] = {
                    "symbol": symbol,
                    "boundary": boundary.isoformat(),
                    "status": "STOOQ_EVIDENCE_UNAVAILABLE",
                    "pre_boundary_count": 0,
                    "on_or_after_boundary_count": 0,
                    "first_trade_date": None,
                    "last_trade_date": None,
                    "stooq_query_symbol": None,
                    "ready_for_promotion": False,
                }
                _persist_checkpoint(checkpoint_path, completed)
                print("    -> STOOQ_EVIDENCE_UNAVAILABLE", flush=True)
                continue

            result = classify_stooq_boundary_evidence(
                symbol=symbol,
                boundary=boundary,
                bars=bars,
            )
            payload = asdict(result)
            payload["boundary"] = result.boundary.isoformat()
            payload["first_trade_date"] = (
                result.first_trade_date.isoformat() if result.first_trade_date else None
            )
            payload["last_trade_date"] = (
                result.last_trade_date.isoformat() if result.last_trade_date else None
            )
            payload["stooq_query_symbol"] = query_symbol
            payload["ready_for_promotion"] = False
            completed[symbol] = payload
            _persist_checkpoint(checkpoint_path, completed)
            print(f"    -> {result.status} via {query_symbol}", flush=True)

        counts = Counter(str(item.get("status")) for item in completed.values())
        summary = {
            "schema_version": "tiingo-stooq-boundary-summary-v0.1",
            "locked_reviewed_symbol_count": len(locked),
            "target_symbol_count": len(rows),
            "completed_symbol_count": len(completed),
            "status_counts": dict(sorted(counts.items())),
            "canonical_state_mutated": False,
            "promotion_authorized": False,
            "provider_calls_made": True,
            "sec_calls_made": False,
            "checkpoint_path": str(checkpoint_path),
            "status": "CHECK_COMPLETE",
            "interpretation": (
                "Stooq evidence may corroborate provider-boundary truncation but does not by itself "
                "prove permanent issuer identity; locked reviewed symbols were excluded."
            ),
        }
        _write(summary_path, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RemainingStooqResolutionError) as exc:
        print(f"remaining Stooq boundary resolution error: {exc}", file=sys.stderr)
        return 2


def _fetch_stooq_bars(
    *,
    adapter: StooqAdapter,
    symbol: str,
    start: date,
    end: date,
    boundary: date,
) -> tuple[tuple[ProviderDailyBar, ...] | None, str | None]:
    """Try Stooq's common US ticker spellings; malformed/no-data CSV is not a campaign failure."""

    for query_symbol in _stooq_query_candidates(symbol):
        try:
            bars = tuple(
                adapter.get_daily_bars(
                    DailyBarRequest(
                        start=start,
                        end=end,
                        provider_symbols=(query_symbol,),
                        adjustment=PriceRepresentation.RAW,
                        run_id=f"stooq-boundary:{symbol}:{boundary.isoformat()}:{query_symbol}",
                    )
                )
            )
        except StooqResponseError:
            continue
        if bars:
            return bars, query_symbol
    return None, None


def _stooq_query_candidates(symbol: str) -> tuple[str, ...]:
    normalized = symbol.strip().upper()
    variants = [f"{normalized}.US", normalized]
    if "." in normalized:
        variants.insert(0, f"{normalized.replace('.', '-')}.US")
    return tuple(dict.fromkeys(variants))


def _persist_checkpoint(path: Path, completed: dict[str, dict[str, object]]) -> None:
    _write(
        path,
        {
            "schema_version": "tiingo-stooq-boundary-checkpoint-v0.1",
            "completed": completed,
            "last_failure": None,
        },
    )


def _locked_symbols(path: Path) -> set[str]:
    candidate = load_reviewed_identity_snapshot_candidate(path)
    return {
        link.query_symbol.strip().upper()
        for link in candidate.provider_series_links
        if link.provider_id == "tiingo"
    }


def _eligible_rows(path: Path, locked: set[str]) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("resolutions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RemainingStooqResolutionError("extended remaining evidence is malformed")
    result: dict[str, dict[str, object]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise RemainingStooqResolutionError("extended remaining row is malformed")
        symbol = _text(raw.get("source_symbol")).upper()
        if symbol in locked:
            continue
        if _text(raw.get("resolution_kind")) != "EXTENDED_SEC_BOUNDARY_NOT_PROVEN":
            continue
        if symbol in result:
            raise RemainingStooqResolutionError(f"duplicate unresolved symbol {symbol}")
        result[symbol] = raw
    return result


def _load_checkpoint(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    completed = payload.get("completed") if isinstance(payload, dict) else None
    if not isinstance(completed, dict):
        raise RemainingStooqResolutionError("Stooq boundary checkpoint is malformed")
    result: dict[str, dict[str, object]] = {}
    for symbol, row in completed.items():
        if not isinstance(symbol, str) or not isinstance(row, dict):
            raise RemainingStooqResolutionError("Stooq checkpoint contains malformed result")
        result[symbol.upper()] = row
    return result


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RemainingStooqResolutionError("required evidence field must be non-empty text")
    return value.strip()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
