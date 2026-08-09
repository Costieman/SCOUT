"""Run a bounded, resumable live evaluation of Alpha Vantage provider behavior."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError

_EVALUATION_ID = "alpha-vantage-live-evaluation-v0.3"
_SNAPSHOT_DATES: tuple[date | None, ...] = (
    date(2014, 7, 10),
    date(2021, 10, 1),
    date(2023, 1, 3),
    None,
)
_BAR_SYMBOLS = ("AAPL", "IBM")


def main() -> int:
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")

    output_root = Path(
        os.environ.get("TRADE_SCOUT_EVALUATION_ROOT", "runtime/alpha-vantage-evaluation")
    )
    report_root = output_root / "report"
    raw_root = output_root / "raw"
    checkpoint_path = report_root / "alpha-vantage-live-evaluation-checkpoint.json"
    report_root.mkdir(parents=True, exist_ok=True)

    delay_seconds = _read_delay_seconds()
    checkpoint = _load_checkpoint(checkpoint_path)
    adapter = AlphaVantageAdapter.from_api_key(api_key, raw_root=raw_root)

    failure: dict[str, Any] | None = None
    for as_of in _SNAPSHOT_DATES:
        task_key = _snapshot_task_key(as_of)
        if task_key in checkpoint["completed_tasks"]:
            continue
        try:
            instruments = tuple(adapter.get_instruments(as_of=as_of))
        except AlphaVantageApiError as exc:
            failure = _failure_record(task_key, exc)
            checkpoint["last_failure"] = failure
            _write_checkpoint(checkpoint_path, checkpoint)
            break
        checkpoint["listing_snapshots"][_snapshot_label(as_of)] = _snapshot_summary(
            as_of, instruments
        )
        checkpoint["completed_tasks"].append(task_key)
        checkpoint["last_failure"] = None
        _write_checkpoint(checkpoint_path, checkpoint)
        _pace(delay_seconds)

    if failure is None and len(checkpoint["listing_snapshots"]) == len(_SNAPSHOT_DATES):
        today = date.today()
        recent_start = today - timedelta(days=30)
        for symbol in _BAR_SYMBOLS:
            task_key = f"daily-bars:{symbol}"
            if task_key in checkpoint["completed_tasks"]:
                continue
            try:
                bars = tuple(
                    adapter.get_daily_bars(
                        DailyBarRequest(
                            start=recent_start,
                            end=today,
                            provider_symbols=(symbol,),
                        )
                    )
                )
            except AlphaVantageApiError as exc:
                failure = _failure_record(task_key, exc)
                checkpoint["last_failure"] = failure
                _write_checkpoint(checkpoint_path, checkpoint)
                break
            checkpoint["recent_daily_bar_samples"][symbol] = _bar_summary(bars)
            checkpoint["completed_tasks"].append(task_key)
            checkpoint["last_failure"] = None
            _write_checkpoint(checkpoint_path, checkpoint)
            _pace(delay_seconds)

    payload = _evaluation_payload(adapter, checkpoint)
    _write_reports(report_root, payload)

    if failure is not None:
        print(
            "Evaluation paused after provider failure. Progress was checkpointed; rerun later to "
            "resume without repeating completed tasks."
        )
        print(f"Failed task: {failure['task']}")
        print(f"Provider error: {failure['error']}")
        return 2

    print((report_root / "alpha-vantage-live-evaluation.md").read_text(encoding="utf-8"))
    return 0


def _read_delay_seconds() -> float:
    raw = os.environ.get("ALPHA_VANTAGE_EVALUATION_DELAY_SECONDS", "0").strip()
    try:
        delay = float(raw)
    except ValueError as exc:
        raise SystemExit("ALPHA_VANTAGE_EVALUATION_DELAY_SECONDS must be numeric") from exc
    if delay < 0:
        raise SystemExit("ALPHA_VANTAGE_EVALUATION_DELAY_SECONDS must be non-negative")
    return delay


def _new_checkpoint() -> dict[str, Any]:
    return {
        "evaluation_id": _EVALUATION_ID,
        "completed_tasks": [],
        "listing_snapshots": {},
        "recent_daily_bar_samples": {},
        "last_failure": None,
    }


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _new_checkpoint()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read evaluation checkpoint: {path}") from exc
    if not isinstance(payload, dict) or payload.get("evaluation_id") != _EVALUATION_ID:
        return _new_checkpoint()
    payload.setdefault("completed_tasks", [])
    payload.setdefault("listing_snapshots", {})
    payload.setdefault("recent_daily_bar_samples", {})
    payload.setdefault("last_failure", None)
    return payload


def _write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _snapshot_task_key(as_of: date | None) -> str:
    return f"listing-snapshot:{_snapshot_label(as_of)}"


def _snapshot_label(as_of: date | None) -> str:
    return as_of.isoformat() if as_of is not None else "latest"


def _failure_record(task_key: str, exc: AlphaVantageApiError) -> dict[str, Any]:
    return {
        "task": task_key,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _pace(delay_seconds: float) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _bar_summary(bars: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "count": len(bars),
        "first_date": bars[0].trade_date.isoformat() if bars else None,
        "last_date": bars[-1].trade_date.isoformat() if bars else None,
        "first_bar": asdict(bars[0]) if bars else None,
        "last_bar": asdict(bars[-1]) if bars else None,
    }


def _evaluation_payload(
    adapter: AlphaVantageAdapter, checkpoint: dict[str, Any]
) -> dict[str, Any]:
    snapshots = [
        checkpoint["listing_snapshots"][label]
        for label in (_snapshot_label(item) for item in _SNAPSHOT_DATES)
        if label in checkpoint["listing_snapshots"]
    ]
    expected_tasks = len(_SNAPSHOT_DATES) + len(_BAR_SYMBOLS)
    completed_tasks = len(checkpoint["completed_tasks"])
    return {
        "evaluation_id": _EVALUATION_ID,
        "provider_id": adapter.provider_id,
        "purpose": "Trade Scout Phase 1 provider evaluation",
        "request_budget": {
            "listing_status_calls": 8,
            "daily_bar_calls": 2,
            "total_expected_calls": 10,
            "note": (
                "A completed listing snapshot requires two provider calls. Checkpointing occurs "
                "after each completed snapshot or daily-bar task."
            ),
        },
        "progress": {
            "completed_tasks": completed_tasks,
            "expected_tasks": expected_tasks,
            "complete": completed_tasks == expected_tasks,
            "last_failure": checkpoint["last_failure"],
        },
        "capabilities": _capabilities_payload(adapter),
        "listing_snapshots": snapshots,
        "recent_daily_bar_samples": checkpoint["recent_daily_bar_samples"],
        "identity_probe": _identity_probe(snapshots),
        "provider_accepted": False,
        "acceptance_note": (
            "This run tests point-in-time listing coverage and recent raw bars only. It does not "
            "establish permanent identity, long-history OHLCV entitlement, corporate-action "
            "quality, licensing/storage rights, or canonical-provider acceptance."
        ),
    }


def _write_reports(report_root: Path, payload: dict[str, Any]) -> None:
    json_path = report_root / "alpha-vantage-live-evaluation.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = report_root / "alpha-vantage-live-evaluation.md"
    markdown_path.write_text(_markdown_report(payload), encoding="utf-8")


def _snapshot_summary(as_of: date | None, instruments: tuple[Any, ...]) -> dict[str, Any]:
    active = [instrument for instrument in instruments if instrument.active]
    delisted = [instrument for instrument in instruments if not instrument.active]
    symbols = {instrument.symbol for instrument in instruments}
    missing_name_symbols = [instrument.symbol for instrument in instruments if not instrument.name]
    warning_symbols = [
        instrument.symbol
        for instrument in instruments
        if instrument.source_fields.get("metadata_quality") == "WARN"
    ]
    suspicious_stock_symbols = [
        instrument.symbol
        for instrument in instruments
        if str(instrument.security_type) == "common_stock"
        and any(token in instrument.symbol for token in ("-P-", "-CL", "-WT", ".W"))
    ]
    return {
        "as_of": _snapshot_label(as_of),
        "total": len(instruments),
        "active_count": len(active),
        "delisted_count": len(delisted),
        "exchange_counts": dict(Counter(instrument.exchange for instrument in instruments)),
        "security_type_counts": dict(
            Counter(str(instrument.security_type) for instrument in instruments)
        ),
        "metadata_quality": {
            "missing_name_count": len(missing_name_symbols),
            "missing_name_rate": len(missing_name_symbols) / len(instruments)
            if instruments
            else 0.0,
            "missing_name_examples": missing_name_symbols[:20],
            "warning_count": len(warning_symbols),
            "symbol_shape_review_count": len(suspicious_stock_symbols),
            "symbol_shape_review_examples": suspicious_stock_symbols[:20],
        },
        "probe_symbols": {
            symbol: symbol in symbols for symbol in ("AAPL", "IBM", "FB", "META", "TWTR")
        },
    }


def _capabilities_payload(adapter: AlphaVantageAdapter) -> dict[str, Any]:
    capabilities = adapter.describe_capabilities()
    return {
        "data_families": sorted(str(item) for item in capabilities.data_families),
        "adjustment_modes": sorted(str(item) for item in capabilities.adjustment_modes),
        "supports_delisted": capabilities.supports_delisted,
        "supports_symbol_history": capabilities.supports_symbol_history,
        "earliest_daily_bar_date": capabilities.earliest_daily_bar_date,
        "known_limitations": list(capabilities.known_limitations),
    }


def _identity_probe(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    by_date = {str(item["as_of"]): item["probe_symbols"] for item in snapshots}
    return {
        "symbol_presence_by_snapshot": by_date,
        "interpretation": (
            "FB/META and TWTR are deliberately inspected as identity/lifecycle stress cases. "
            "Presence or absence does not prove continuity; Alpha Vantage LISTING_STATUS supplies "
            "dated symbols, but the adapter does not infer that different symbols identify the "
            "same security."
        ),
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    progress = payload["progress"]
    table_header = (
        "| as-of | total | active | delisted | missing names | review symbols | "
        "AAPL | FB | META | TWTR |"
    )
    lines = [
        "# Alpha Vantage live evaluation",
        "",
        f"Provider: `{payload['provider_id']}`",
        "",
        "## Progress",
        "",
        f"Completed tasks: {progress['completed_tasks']} / {progress['expected_tasks']}",
        "",
    ]
    if progress["last_failure"] is not None:
        failure = progress["last_failure"]
        lines.extend(
            [
                f"Paused at: `{failure['task']}`",
                "",
                f"Provider error: `{failure['error']}`",
                "",
                "The evaluation is resumable; completed tasks will be skipped on the next run.",
                "",
            ]
        )
    lines.extend(
        [
            "## Point-in-time listing snapshots",
            "",
            table_header,
            "|---|---:|---:|---:|---:|---:|---|---|---|---|",
        ]
    )
    for snapshot in payload["listing_snapshots"]:
        probes = snapshot["probe_symbols"]
        quality = snapshot["metadata_quality"]
        lines.append(
            f"| {snapshot['as_of']} | {snapshot['total']} | {snapshot['active_count']} | "
            f"{snapshot['delisted_count']} | {quality['missing_name_count']} | "
            f"{quality['symbol_shape_review_count']} | {probes['AAPL']} | {probes['FB']} | "
            f"{probes['META']} | {probes['TWTR']} |"
        )

    lines.extend(["", "## Listing metadata quality", ""])
    for snapshot in payload["listing_snapshots"]:
        quality = snapshot["metadata_quality"]
        missing_rate = 100 * quality["missing_name_rate"]
        lines.append(
            f"- **{snapshot['as_of']}:** {quality['missing_name_count']} blank names "
            f"({missing_rate:.3f}%); {quality['symbol_shape_review_count']} symbols flagged for "
            "security-type review."
        )
        if quality["missing_name_examples"]:
            examples = ", ".join(quality["missing_name_examples"][:10])
            lines.append(f"  Missing-name examples: `{examples}`")
        if quality["symbol_shape_review_examples"]:
            examples = ", ".join(quality["symbol_shape_review_examples"][:10])
            lines.append(f"  Symbol-shape review examples: `{examples}`")

    lines.extend(["", "## Recent daily-bar samples", ""])
    for symbol, sample in payload["recent_daily_bar_samples"].items():
        date_range = f"{sample['first_date']} to {sample['last_date']}"
        lines.append(f"- **{symbol}:** {sample['count']} bars, {date_range}")
    if not payload["recent_daily_bar_samples"]:
        lines.append("- Not reached yet.")

    lines.extend(
        [
            "",
            "## Acceptance status",
            "",
            "**NOT ACCEPTED.** " + str(payload["acceptance_note"]),
            "",
            "Blank company names are reference-metadata warnings, not fatal universe errors. "
            "Security-type labels remain provisional and require reconciliation before eligibility "
            "filtering is trusted.",
            "",
            "The strongest question tested by this run is whether `LISTING_STATUS` can support a "
            "2010-present point-in-time universe layer. Permanent security identity, corporate "
            "actions, full historical OHLCV, and licensing remain separate gates.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
