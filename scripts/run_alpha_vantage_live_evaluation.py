"""Run a bounded live evaluation of Alpha Vantage listing-status and recent daily bars."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter


def main() -> int:
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")

    output_root = Path(
        os.environ.get("TRADE_SCOUT_EVALUATION_ROOT", "runtime/alpha-vantage-evaluation")
    )
    report_root = output_root / "report"
    raw_root = output_root / "raw"
    report_root.mkdir(parents=True, exist_ok=True)

    adapter = AlphaVantageAdapter.from_api_key(api_key, raw_root=raw_root)

    snapshots = []
    for as_of in (
        date(2014, 7, 10),
        date(2021, 10, 1),
        date(2023, 1, 3),
        None,
    ):
        instruments = tuple(adapter.get_instruments(as_of=as_of))
        snapshots.append(_snapshot_summary(as_of, instruments))

    today = date.today()
    recent_start = today - timedelta(days=30)
    bar_samples: dict[str, Any] = {}
    for symbol in ("AAPL", "IBM"):
        bars = tuple(
            adapter.get_daily_bars(
                DailyBarRequest(
                    start=recent_start,
                    end=today,
                    provider_symbols=(symbol,),
                )
            )
        )
        bar_samples[symbol] = {
            "count": len(bars),
            "first_date": bars[0].trade_date.isoformat() if bars else None,
            "last_date": bars[-1].trade_date.isoformat() if bars else None,
            "first_bar": asdict(bars[0]) if bars else None,
            "last_bar": asdict(bars[-1]) if bars else None,
        }

    payload = {
        "evaluation_id": "alpha-vantage-live-evaluation-v0.1",
        "provider_id": adapter.provider_id,
        "purpose": "Trade Scout Phase 1 provider evaluation",
        "request_budget": {
            "listing_status_calls": 8,
            "daily_bar_calls": 2,
            "total_expected_calls": 10,
        },
        "capabilities": _capabilities_payload(adapter),
        "listing_snapshots": snapshots,
        "recent_daily_bar_samples": bar_samples,
        "identity_probe": _identity_probe(snapshots),
        "provider_accepted": False,
        "acceptance_note": (
            "This run tests point-in-time listing coverage and recent raw bars only. It does not "
            "establish permanent identity, long-history OHLCV entitlement, corporate-action quality, "
            "licensing/storage rights, or canonical-provider acceptance."
        ),
    }

    json_path = report_root / "alpha-vantage-live-evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    markdown_path = report_root / "alpha-vantage-live-evaluation.md"
    markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _snapshot_summary(as_of: date | None, instruments: tuple[Any, ...]) -> dict[str, Any]:
    active = [instrument for instrument in instruments if instrument.active]
    delisted = [instrument for instrument in instruments if not instrument.active]
    symbols = {instrument.symbol for instrument in instruments}
    return {
        "as_of": as_of.isoformat() if as_of is not None else "latest",
        "total": len(instruments),
        "active_count": len(active),
        "delisted_count": len(delisted),
        "exchange_counts": dict(Counter(instrument.exchange for instrument in instruments)),
        "security_type_counts": dict(
            Counter(str(instrument.security_type) for instrument in instruments)
        ),
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
            "dated symbols but the adapter does not infer that different symbols are the same security."
        ),
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Alpha Vantage live evaluation",
        "",
        f"Provider: `{payload['provider_id']}`",
        "",
        "## Point-in-time listing snapshots",
        "",
        "| as-of | total | active | delisted | AAPL | FB | META | TWTR |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for snapshot in payload["listing_snapshots"]:
        probes = snapshot["probe_symbols"]
        lines.append(
            f"| {snapshot['as_of']} | {snapshot['total']} | {snapshot['active_count']} | "
            f"{snapshot['delisted_count']} | {probes['AAPL']} | {probes['FB']} | "
            f"{probes['META']} | {probes['TWTR']} |"
        )
    lines.extend(
        [
            "",
            "## Recent daily-bar samples",
            "",
        ]
    )
    for symbol, sample in payload["recent_daily_bar_samples"].items():
        lines.append(
            f"- **{symbol}:** {sample['count']} bars, {sample['first_date']} to {sample['last_date']}"
        )
    lines.extend(
        [
            "",
            "## Acceptance status",
            "",
            "**NOT ACCEPTED.** " + str(payload["acceptance_note"]),
            "",
            "The strongest question tested by this run is whether `LISTING_STATUS` can support a "
            "2010-present point-in-time universe layer. Permanent security identity, corporate actions, "
            "full historical OHLCV, and licensing remain separate gates.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
