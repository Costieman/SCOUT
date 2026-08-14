"""Diagnose unresolved Tiingo identities that begin at the campaign left boundary.

Read-only with respect to canonical state. The script inspects SEC annual filings around the
1996-01-02 campaign boundary and records why the existing conservative resolver could not prove
continuity. It is diagnostic evidence for the next resolver rule, not an approval mechanism.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from trade_scout.data.auto_identity_import import (
    AutoIdentityImportError,
    SecIdentityClient,
    _EXCHANGE_TERMS,
    _load_all_filings,
    _normalize,
    load_sec_catalog,
)

_CAMPAIGN_START = date(1996, 1, 2)
_LOOKBACK = timedelta(days=1100)
_LOOKAHEAD = timedelta(days=730)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--sec-user-agent",
        default=os.environ.get("SCOUT_SEC_USER_AGENT"),
    )
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
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("resolution_kind") == "BOUNDARY_NOT_PROVEN"
        and row.get("observed_first_date") == _CAMPAIGN_START.isoformat()
    ]

    client = SecIdentityClient(
        user_agent=args.sec_user_agent,
        minimum_interval_seconds=args.sleep,
    )
    catalog = load_sec_catalog(client)
    diagnostics: list[dict[str, object]] = []

    for index, row in enumerate(targets, start=1):
        symbol = str(row["source_symbol"]).upper()
        print(f"[{index}/{len(targets)}] {symbol}: campaign-boundary diagnostic", flush=True)
        company = catalog.get(symbol) or catalog.get(symbol.replace(".", "-"))
        if company is None:
            diagnostics.append({"symbol": symbol, "classification": "NO_SEC_TICKER_MATCH"})
            continue

        try:
            filings = _load_all_filings(client, company.cik)
        except AutoIdentityImportError as exc:
            diagnostics.append(
                {"symbol": symbol, "classification": "SEC_SOURCE_ERROR", "detail": str(exc)}
            )
            continue

        window = [
            filing
            for filing in filings
            if _CAMPAIGN_START - _LOOKBACK
            <= filing.filing_date
            <= _CAMPAIGN_START + _LOOKAHEAD
        ]
        pre = [f for f in window if f.filing_date <= _CAMPAIGN_START]
        post = [f for f in window if f.filing_date >= _CAMPAIGN_START]
        terms = _EXCHANGE_TERMS.get(company.exchange, ())
        ticker_re = re.compile(
            rf"(?<![a-z0-9]){re.escape(company.ticker.lower())}(?![a-z0-9])"
        )

        pre_ticker = pre_exchange = pre_same = 0
        post_same = 0
        evidence_urls: list[str] = []
        for filing, is_pre in [(f, True) for f in pre] + [(f, False) for f in post]:
            try:
                text = _normalize(client.get_text(filing.source_url))
            except AutoIdentityImportError:
                continue
            has_ticker = ticker_re.search(text) is not None
            has_exchange = any(term in text for term in terms)
            if is_pre:
                pre_ticker += int(has_ticker)
                pre_exchange += int(has_exchange)
                if has_ticker and has_exchange:
                    pre_same += 1
                    evidence_urls.append(filing.source_url)
            elif has_ticker and has_exchange:
                post_same += 1

        if pre_same:
            classification = "PRE_BOUNDARY_SAME_FILING_TICKER_EXCHANGE"
        elif pre_ticker and pre_exchange:
            classification = "PRE_BOUNDARY_EVIDENCE_SPLIT_ACROSS_FILINGS"
        elif not pre:
            classification = "NO_PRE_BOUNDARY_ANNUAL_FILING"
        elif pre_ticker:
            classification = "PRE_BOUNDARY_TICKER_ONLY"
        elif pre_exchange:
            classification = "PRE_BOUNDARY_EXCHANGE_ONLY"
        elif post_same:
            classification = "POST_BOUNDARY_ONLY"
        else:
            classification = "NO_TICKER_EXCHANGE_EVIDENCE_IN_WINDOW"

        diagnostics.append(
            {
                "symbol": symbol,
                "cik": company.cik,
                "exchange": company.exchange,
                "classification": classification,
                "pre_filing_count": len(pre),
                "post_filing_count": len(post),
                "pre_ticker_filing_count": pre_ticker,
                "pre_exchange_filing_count": pre_exchange,
                "pre_same_filing_count": pre_same,
                "post_same_filing_count": post_same,
                "evidence_urls": evidence_urls,
            }
        )

    counts = Counter(str(item["classification"]) for item in diagnostics)
    output = {
        "schema_version": "tiingo-campaign-boundary-diagnostic-v0.1",
        "campaign_start": _CAMPAIGN_START.isoformat(),
        "target_count": len(targets),
        "classification_counts": dict(sorted(counts.items())),
        "diagnostics": diagnostics,
        "canonical_state_mutated": False,
    }
    out = root / "evidence" / "deferred-resolution" / "campaign-boundary-diagnostic.json"
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "diagnostics"}, indent=2, sort_keys=True))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
