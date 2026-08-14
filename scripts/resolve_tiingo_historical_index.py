"""Resolve 1996 Tiingo campaign-boundary deferrals with SEC historical full indexes.

Read-only with respect to canonical state.  It reuses the current deferred-resolution evidence,
loads the SEC 1994Q3-1996Q1 full indexes once, and checks original same-CIK filings for ticker and
exchange continuity.  Newly proven cases are written to evidence for later batch promotion.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from trade_scout.data.auto_identity_import import SecIdentityClient, load_sec_catalog
from trade_scout.data.sec_historical_index import (
    HistoricalBoundaryEvidence,
    load_full_index_window,
    resolve_historical_campaign_boundary,
)

_CAMPAIGN_START = date(1996, 1, 2)
_INDEX_START = date(1994, 7, 1)
_INDEX_END = date(1996, 3, 31)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sec-user-agent", default=os.environ.get("SCOUT_SEC_USER_AGENT"))
    parser.add_argument("--sleep", type=float, default=0.6)
    args = parser.parse_args()
    if not isinstance(args.sec_user_agent, str) or "@" not in args.sec_user_agent:
        parser.error("--sec-user-agent or SCOUT_SEC_USER_AGENT with contact email is required")

    root = args.root.expanduser().resolve()
    remaining_path = root / "evidence" / "deferred-resolution" / "remaining.json"
    payload = json.loads(remaining_path.read_text(encoding="utf-8"))
    rows = payload.get("resolutions")
    if not isinstance(rows, list):
        raise SystemExit("remaining.json has unsupported structure")

    targets = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("resolution_kind") == "CAMPAIGN_BOUNDARY_NOT_PROVEN"
        and row.get("observed_first_date") == _CAMPAIGN_START.isoformat()
    ]

    client = SecIdentityClient(user_agent=args.sec_user_agent, minimum_interval_seconds=args.sleep)
    catalog = load_sec_catalog(client)
    print("Loading SEC historical full indexes 1994Q3 through 1996Q1...", flush=True)
    index_rows = load_full_index_window(client, start=_INDEX_START, end=_INDEX_END)
    print(f"Loaded {len(index_rows)} indexed SEC filings in historical window.", flush=True)

    results: list[HistoricalBoundaryEvidence] = []
    for index, row in enumerate(targets, start=1):
        symbol = str(row["source_symbol"]).upper()
        print(f"[{index}/{len(targets)}] {symbol}: historical-index evidence", flush=True)
        company = catalog.get(symbol) or catalog.get(symbol.replace(".", "-"))
        if company is None:
            result = HistoricalBoundaryEvidence(
                symbol=symbol,
                cik=int(row["cik"]) if row.get("cik") is not None else 0,
                status="DEFERRED",
                kind="NO_SEC_TICKER_MATCH",
                pre_boundary_url=None,
                post_boundary_url=None,
                reason="current SEC ticker catalog has no unique match",
            )
        else:
            result = resolve_historical_campaign_boundary(
                client=client,
                company=company,
                boundary=_CAMPAIGN_START,
                index_rows=index_rows,
            )
        results.append(result)
        print(f"    -> {result.status} {result.kind}", flush=True)

    ready = [r for r in results if r.ready]
    deferred = [r for r in results if not r.ready]
    output_root = root / "evidence" / "deferred-resolution" / "historical-index"
    output_root.mkdir(parents=True, exist_ok=True)
    _write(output_root / "ready.json", ready)
    _write(output_root / "remaining.json", deferred)
    summary = {
        "schema_version": "tiingo-sec-historical-index-resolution-v0.1",
        "target_count": len(targets),
        "ready_count": len(ready),
        "deferred_count": len(deferred),
        "ready_kind_counts": dict(sorted(Counter(r.kind for r in ready).items())),
        "deferred_kind_counts": dict(sorted(Counter(r.kind for r in deferred).items())),
        "canonical_state_mutated": False,
        "index_start": _INDEX_START.isoformat(),
        "index_end": _INDEX_END.isoformat(),
        "indexed_filing_count": len(index_rows),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"report: {output_root / 'summary.json'}")
    return 0


def _write(path: Path, rows: list[HistoricalBoundaryEvidence]) -> None:
    payload = {
        "count": len(rows),
        "evidence": [
            {
                "symbol": r.symbol,
                "cik": r.cik,
                "status": r.status,
                "kind": r.kind,
                "pre_boundary_url": r.pre_boundary_url,
                "post_boundary_url": r.post_boundary_url,
                "reason": r.reason,
            }
            for r in rows
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
