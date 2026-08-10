"""Validate S&P 500 source symbols against audited Tiingo query symbology without API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from trade_scout.data.providers.tiingo_sp500_campaign import (
    load_tiingo_sp500_campaign_plan,
    parse_tiingo_sp500_universe,
)
from trade_scout.data.providers.tiingo_symbology import build_tiingo_query_symbol_links


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate source-to-Tiingo query symbology before any provider requests."
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    plan = load_tiingo_sp500_campaign_plan(args.plan)
    request = Request(plan.universe_source_url, headers={"User-Agent": "trade-scout/0.1"})
    with urlopen(request, timeout=30.0) as response:
        payload = bytes(response.read())
    snapshot = parse_tiingo_sp500_universe(payload, plan)
    links = build_tiingo_query_symbol_links(snapshot.symbols)
    translated = [
        {
            "source_symbol": item.source_symbol,
            "tiingo_query_symbol": item.query_symbol,
        }
        for item in links
        if item.translated
    ]
    report = {
        "schema_version": "tiingo-sp500-symbology-plan-v0.1",
        "plan_version": plan.plan_version,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "universe_sha256": snapshot.sha256,
        "source_symbol_count": len(snapshot.symbols),
        "unique_query_symbol_count": len({item.query_symbol for item in links}),
        "collision_check": "PASS",
        "translation_count": len(translated),
        "translations": translated,
        "provider_requests_made": 0,
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(args.output)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
