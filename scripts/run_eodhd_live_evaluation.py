"""Run a bounded EODHD candidate evaluation without declaring provider acceptance."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from trade_scout.data.contracts import CorporateActionType, PriceRepresentation
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest
from trade_scout.data.providers.eodhd import EodhdAdapter, EodhdInstrumentLink


def main() -> int:
    token = os.environ.get("EODHD_API_KEY", "").strip()
    if not token:
        raise SystemExit("EODHD_API_KEY is not configured")

    root = Path("runtime/eodhd-evaluation")
    report_root = root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    today = date.today()
    start = today - timedelta(days=30)

    adapter = EodhdAdapter.from_api_token(
        token,
        instrument_links=(EodhdInstrumentLink("AAPL.US", "eodhd:isin:US0378331005"),),
        raw_root=root / "raw",
    )

    capabilities = adapter.describe_capabilities()
    active = tuple(adapter._instrument_rows(delisted=False))
    delisted = tuple(adapter._instrument_rows(delisted=True))
    bars = tuple(
        adapter.get_daily_bars(
            DailyBarRequest(
                start=start,
                end=today,
                provider_symbols=("AAPL.US",),
                adjustment=PriceRepresentation.RAW,
                run_id="eodhd-live-evaluation:aapl-recent",
            )
        )
    )
    actions = tuple(
        adapter.get_corporate_actions(
            CorporateActionRequest(
                start=start,
                end=today,
                provider_symbols=("AAPL.US",),
            )
        )
    )

    active_isin = sum(bool(row.get("Isin")) for row in active)
    delisted_isin = sum(bool(row.get("Isin")) for row in delisted)
    payload = {
        "evaluation_id": "eodhd-live-evaluation-v0.1",
        "provider_id": "eodhd",
        "evaluated_on": today.isoformat(),
        "active_symbol_count": len(active),
        "active_isin_count": active_isin,
        "delisted_symbol_count": len(delisted),
        "delisted_isin_count": delisted_isin,
        "recent_aapl_bar_count": len(bars),
        "recent_aapl_first_date": bars[0].trade_date.isoformat() if bars else None,
        "recent_aapl_last_date": bars[-1].trade_date.isoformat() if bars else None,
        "recent_aapl_action_count": len(actions),
        "recent_aapl_split_count": sum(
            action.action_type is CorporateActionType.SPLIT for action in actions
        ),
        "recent_aapl_dividend_count": sum(
            action.action_type is CorporateActionType.CASH_DIVIDEND for action in actions
        ),
        "capabilities": {
            "data_families": sorted(item.value for item in capabilities.data_families),
            "adjustment_modes": sorted(item.value for item in capabilities.adjustment_modes),
            "supports_delisted": capabilities.supports_delisted,
            "supports_symbol_history": capabilities.supports_symbol_history,
            "known_limitations": list(capabilities.known_limitations),
        },
        "sample_bar": asdict(bars[-1]) if bars else None,
        "provider_accepted": False,
        "acceptance_note": (
            "This bounded run only characterizes current inventory, delisted inventory, recent raw "
            "OHLCV, identity fields, and recent corporate-action access. Paid multi-year history, "
            "split-only adjustment reconstruction, symbol continuity, licensing fit, and "
            "cross-provider validation remain separate acceptance gates."
        ),
    }
    if payload["sample_bar"] is not None:
        sample_bar = payload["sample_bar"]
        if isinstance(sample_bar, dict):
            sample_bar["trade_date"] = sample_bar["trade_date"].isoformat()

    json_path = report_root / "eodhd-live-evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "eodhd-live-evaluation.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _markdown(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "# EODHD Phase 1 candidate evaluation",
            "",
            f"Active symbols: {payload['active_symbol_count']}",
            f"Active symbols with ISIN: {payload['active_isin_count']}",
            f"Delisted symbols: {payload['delisted_symbol_count']}",
            f"Delisted symbols with ISIN: {payload['delisted_isin_count']}",
            f"Recent AAPL bars: {payload['recent_aapl_bar_count']}",
            f"Recent AAPL actions: {payload['recent_aapl_action_count']}",
            "",
            "**Provider accepted: false.** " + str(payload["acceptance_note"]),
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
