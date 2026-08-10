"""Exercise Tiingo split-only normalization against a known live split window."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest
from trade_scout.data.providers.tiingo import TiingoAdapter, TiingoInstrumentLink
from trade_scout.data.providers.tiingo_adjustments import apply_tiingo_split_adjustments

OUTPUT = Path("runtime/tiingo-manifesto-evaluation/split-normalization.json")


def main() -> int:
    token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("TIINGO_API_TOKEN is not configured")

    adapter = TiingoAdapter.from_api_token(
        token,
        instrument_links=(
            TiingoInstrumentLink(
                query_symbol="AAPL",
                provider_instrument_id="tiingo:probe:AAPL",
            ),
        ),
    )
    start = date(2020, 8, 27)
    end = date(2020, 9, 2)
    bars = tuple(
        adapter.get_daily_bars(
            DailyBarRequest(
                start=start,
                end=end,
                provider_symbols=("AAPL",),
                adjustment=PriceRepresentation.RAW,
                run_id="tiingo-manifesto-split-probe",
            )
        )
    )
    actions = tuple(
        adapter.get_corporate_actions(
            CorporateActionRequest(start=start, end=end, provider_symbols=("AAPL",))
        )
    )
    adjusted = apply_tiingo_split_adjustments(
        bars,
        actions,
        adjustment_anchor_date=end,
    )
    by_date = {bar.trade_date: bar for bar in adjusted}
    pre = by_date.get(date(2020, 8, 28))
    effective = by_date.get(date(2020, 8, 31))
    passed = (
        pre is not None
        and effective is not None
        and pre.split_factor == 0.25
        and effective.split_factor == 1.0
        and len([action for action in actions if action.action_type.value == "split"]) == 1
    )
    report = {
        "evaluation_id": "tiingo-split-normalization-live-v0.1",
        "symbol": "AAPL",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "bar_count": len(bars),
        "split_action_count": len(
            [action for action in actions if action.action_type.value == "split"]
        ),
        "pre_split_factor": pre.split_factor if pre is not None else None,
        "effective_date_factor": effective.split_factor if effective is not None else None,
        "expected_pre_split_factor": 0.25,
        "expected_effective_date_factor": 1.0,
        "pass": passed,
        "raw_prices_emitted": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
