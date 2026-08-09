"""Collect bounded SEC issuer-reference evidence for reviewed Stooq identity claims."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from trade_scout.data.free_stack_identity import (
    FreeStackIdentityState,
    StooqIdentityClaim,
    reconcile_stooq_claim_with_sec,
)
from trade_scout.data.providers.sec_edgar import SecEdgarAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile explicitly reviewed Stooq ticker/exchange claims against the current SEC "
            "ticker association file. Results are issuer-reference evidence only."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_specs",
        required=True,
        help="Repeatable STOOQ_SYMBOL,LINK_ID,TICKER,EXCHANGE specification.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/free-stack-identity-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit(
            "SEC_EDGAR_USER_AGENT is not configured; use a declared application/contact identity"
        )

    claims = tuple(_parse_case(spec) for spec in args.case_specs)
    keys = [(claim.query_symbol.upper(), claim.provider_instrument_id) for claim in claims]
    if len(keys) != len(set(keys)):
        raise SystemExit("free-stack identity evidence cases must be unique")

    output_root: Path = args.output_root
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    adapter = SecEdgarAdapter.from_user_agent(user_agent, raw_root=output_root / "raw")
    associations = tuple(adapter._client.get_ticker_associations())
    evidence = tuple(reconcile_stooq_claim_with_sec(claim, associations) for claim in claims)

    unique_count = sum(
        item.state is FreeStackIdentityState.UNIQUE_ISSUER_REFERENCE for item in evidence
    )
    unresolved_count = len(evidence) - unique_count
    payload = {
        "report_type": "free-stack-identity-evidence-v0.1",
        "sec_reference_snapshot": "current",
        "case_count": len(evidence),
        "unique_issuer_reference_count": unique_count,
        "unresolved_count": unresolved_count,
        "cases": [asdict(item) for item in evidence],
        "canonical_identity_promoted": False,
        "interpretation": (
            "A unique result establishes only that an externally reviewed Stooq ticker/exchange "
            "claim has one current SEC issuer association. CIK is issuer-level, not a permanent "
            "security identifier, and current associations cannot be back-projected historically."
        ),
    }
    json_path = report_root / "free-stack-identity-evidence.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = report_root / "free-stack-identity-evidence.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if unresolved_count == 0 else 2


def _parse_case(spec: str) -> StooqIdentityClaim:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 4:
        raise SystemExit("--case must be STOOQ_SYMBOL,LINK_ID,TICKER,EXCHANGE")
    return StooqIdentityClaim(
        query_symbol=parts[0],
        provider_instrument_id=parts[1],
        ticker=parts[2],
        exchange=parts[3],
    )


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Free-stack identity evidence",
        "",
        f"Cases: **{payload['case_count']}**",
        f"Unique current SEC issuer references: **{payload['unique_issuer_reference_count']}**",
        f"Unresolved: **{payload['unresolved_count']}**",
        "",
        "| Stooq symbol | reviewed ticker | exchange | SEC CIKs | state |",
        "|---|---|---|---|---|",
    ]
    cases = payload.get("cases")
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, dict):
                lines.append(
                    f"| {case['query_symbol']} | {case['reviewed_ticker']} | "
                    f"{case['reviewed_exchange']} | {case['sec_ciks']} | {case['state']} |"
                )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            str(payload["interpretation"]),
            "",
            "**No canonical security identity is promoted by this report.**",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
