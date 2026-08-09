"""Freeze a deterministic representative-scale EODHD campaign plan from live inventory."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from trade_scout.data.providers.eodhd import EodhdAdapter
from trade_scout.data.providers.eodhd_representative_sample import (
    EodhdRepresentativeSamplePolicy,
    campaign_payload,
    select_eodhd_representative_sample,
)

_DEFAULT_OUTPUT = Path("runtime/eodhd-representative-plan/eodhd-phase1-representative-v0.1.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select a deterministic ISIN-backed common-stock sample from current EODHD active "
            "and delisted inventories and write a frozen campaign plan outside Git."
        )
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--active-count", type=int, default=500)
    parser.add_argument("--delisted-count", type=int, default=25)
    parser.add_argument("--min-exchanges", type=int, default=2)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2015, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument(
        "--seed",
        default="trade-scout-phase1-eodhd-representative-v0.1",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    token = (
        os.environ.get("EODHD_API_TOKEN", "").strip()
        or os.environ.get("EODHD_API_KEY", "").strip()
    )
    if not token:
        raise SystemExit("EODHD_API_TOKEN or EODHD_API_KEY is not configured")

    adapter = EodhdAdapter.from_api_token(
        token,
        raw_root=args.output.parent / "raw-inventory",
    )
    instruments = tuple(adapter.get_instruments())
    policy = EodhdRepresentativeSamplePolicy(
        active_count=args.active_count,
        delisted_count=args.delisted_count,
        min_exchanges=args.min_exchanges,
        start=args.start,
        end=args.end,
        seed=args.seed,
    )
    selection = select_eodhd_representative_sample(instruments, policy=policy)
    payload = campaign_payload(selection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("# EODHD representative campaign plan")
    print()
    print(f"Active common stocks: {len(selection.active)}")
    print(f"Delisted common stocks: {len(selection.delisted)}")
    print(f"Exchange count: {len(selection.exchanges)}")
    print(f"Exchanges: {', '.join(selection.exchanges)}")
    print(f"History window: {policy.start.isoformat()} to {policy.end.isoformat()}")
    print(f"Frozen plan: {args.output}")
    print()
    print("This command only freezes the sample. It does not accept EODHD or Phase 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
