"""Run one bounded local Tiingo S&P 500 acquisition slice.

Raw licensed responses are persisted only under the caller's local runtime root. The report
contains derived progress metadata and is safe to inspect separately from raw provider data.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from trade_scout.data.providers.tiingo import TiingoHttpClient, TiingoRawStoreCapture
from trade_scout.data.providers.tiingo_sp500_campaign import (
    load_tiingo_sp500_campaign_plan,
    parse_tiingo_sp500_universe,
    run_tiingo_sp500_campaign,
)
from trade_scout.data.raw_store import RawBatchStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path("runtime/tiingo-sp500-campaign"),
    )
    parser.add_argument("--max-symbols", type=int, default=None)
    args = parser.parse_args()

    token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("TIINGO_API_TOKEN is not configured")

    plan = load_tiingo_sp500_campaign_plan(args.plan)
    request = Request(plan.universe_source_url, headers={"User-Agent": "trade-scout/0.1"})
    with urlopen(request, timeout=30.0) as response:
        universe_payload = bytes(response.read())
    snapshot = parse_tiingo_sp500_universe(universe_payload, plan)

    raw_root = args.runtime_root / "raw"
    client = TiingoHttpClient(
        token,
        raw_capture=TiingoRawStoreCapture(RawBatchStore(raw_root)),
    )
    result = run_tiingo_sp500_campaign(
        client,
        plan,
        snapshot,
        args.runtime_root / "checkpoint.json",
        max_symbols_this_run=args.max_symbols,
    )
    report = {
        "plan_version": result.plan_version,
        "universe_snapshot_date": snapshot.snapshot_date.isoformat(),
        "universe_sha256": result.universe_sha256,
        "universe_constituent_count": len(snapshot.symbols),
        "completed_symbol_count": result.completed_symbol_count,
        "pending_symbol_count": result.pending_symbol_count,
        "executed_symbol_count": result.executed_symbol_count,
        "acquired_row_count": result.acquired_row_count,
        "rate_limited": result.rate_limited,
        "rate_limited_symbol": result.rate_limited_symbol,
        "failed_symbol": result.failed_symbol,
        "failure_type": result.failure_type,
        "canonical_dataset_written": False,
        "raw_root": str(raw_root),
    }
    report_path = args.runtime_root / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_path)
    return 1 if result.failed_symbol is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
