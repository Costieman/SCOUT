"""Run a bounded live evaluation of SEC EDGAR issuer/reference data."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from trade_scout.data.providers.sec_edgar import SecEdgarAdapter

_PROBE_CIKS = {
    "AAPL": 320193,
    "META": 1326801,
}


def main() -> int:
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit(
            "SEC_EDGAR_USER_AGENT is not configured; use a declared application/contact identity"
        )

    output_root = Path(os.environ.get("TRADE_SCOUT_EVALUATION_ROOT", "runtime/sec-edgar-evaluation"))
    report_root = output_root / "report"
    raw_root = output_root / "raw"
    report_root.mkdir(parents=True, exist_ok=True)

    adapter = SecEdgarAdapter.from_user_agent(user_agent, raw_root=raw_root)
    instruments = tuple(adapter.get_instruments())

    issuer_probes: dict[str, Any] = {}
    for symbol, cik in _PROBE_CIKS.items():
        metadata = adapter.get_issuer_metadata(cik)
        issuer_probes[symbol] = {
            "cik": cik,
            "name": metadata.get("name"),
            "tickers": metadata.get("tickers"),
            "exchanges": metadata.get("exchanges"),
            "former_names": metadata.get("formerNames"),
        }

    cik_counts = Counter(int(item.source_fields["cik"]) for item in instruments)
    payload = {
        "evaluation_id": "sec-edgar-reference-evaluation-v0.1",
        "provider_id": adapter.provider_id,
        "purpose": "Trade Scout Phase 1 issuer/reference validation",
        "current_associations": {
            "count": len(instruments),
            "exchange_counts": dict(Counter(item.exchange for item in instruments)),
            "unique_cik_count": len(cik_counts),
            "multi_ticker_cik_count": sum(count > 1 for count in cik_counts.values()),
            "multi_ticker_cik_examples": [
                cik for cik, count in cik_counts.most_common(20) if count > 1
            ],
        },
        "issuer_probes": issuer_probes,
        "capabilities": {
            "known_limitations": list(adapter.describe_capabilities().known_limitations),
            "supports_symbol_history": adapter.describe_capabilities().supports_symbol_history,
            "supports_delisted": adapter.describe_capabilities().supports_delisted,
        },
        "identity_conclusion": (
            "SEC CIK is useful issuer-level identity and reconciliation metadata, but it is not a "
            "permanent security identifier. Current ticker/exchange associations and former issuer "
            "names must not be back-projected into historical security identity."
        ),
        "provider_accepted_as_security_master": False,
    }

    json_path = report_root / "sec-edgar-reference-evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    markdown_path = report_root / "sec-edgar-reference-evaluation.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _markdown(payload: dict[str, Any]) -> str:
    associations = payload["current_associations"]
    lines = [
        "# SEC EDGAR reference evaluation",
        "",
        f"Current ticker/exchange associations: {associations['count']}",
        f"Unique issuer CIKs: {associations['unique_cik_count']}",
        f"CIKs associated with multiple current tickers: {associations['multi_ticker_cik_count']}",
        "",
        "## Issuer probes",
        "",
    ]
    for symbol, probe in payload["issuer_probes"].items():
        lines.append(
            f"- **{symbol}** — CIK {probe['cik']}; name={probe['name']}; "
            f"tickers={probe['tickers']}; exchanges={probe['exchanges']}"
        )
        if probe["former_names"]:
            lines.append(f"  Former issuer names: {probe['former_names']}")
    lines.extend(
        [
            "",
            "## Identity conclusion",
            "",
            str(payload["identity_conclusion"]),
            "",
            "**NOT ACCEPTED as a canonical security master.** SEC EDGAR remains a specialist "
            "issuer/reference source for reconciliation and provenance.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
