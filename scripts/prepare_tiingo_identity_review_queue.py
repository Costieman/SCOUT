"""Prepare a prioritized review queue from durable Tiingo profile evidence.

This script performs no provider calls and makes no identity decisions. It turns the private
profile plus the current reviewed candidate into a deterministic worklist so sourced identity
review can proceed in large batches without repeatedly reconstructing symbol lists by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
)

_DEFERRED_SYMBOLS = frozenset(
    {
        "ALGN",
        "ARES",
        "BAC",
        "BKNG",
        "BLDR",
        "CARR",
        "COST",
        "HON",
        "JPM",
        "MRK",
        "MS",
        "XOM",
    }
)


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatorWorkspaceError(f"unable to read Tiingo profile {path}: {exc}") from exc
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise OperatorWorkspaceError("Tiingo profile does not contain a symbols array")
    return payload


def _priority(first_date: str, row_count: int) -> tuple[int, str, int]:
    """Prefer campaign-start histories, then older/larger histories.

    This is triage only. Priority never implies that identity continuity is safe to promote.
    """

    campaign_start = first_date == "1996-01-02"
    return (0 if campaign_start else 1, first_date, -row_count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError("durable workspace verification is inconsistent")

        profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
        candidate_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        profile = _load_profile(profile_path)
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
    except (OperatorWorkspaceError, ReviewedIdentitySnapshotError) as exc:
        print(f"Tiingo identity review queue error: {exc}", file=sys.stderr)
        return 2

    reviewed = {
        item.query_symbol.upper()
        for item in candidate.provider_series_links
        if item.provider_id == "tiingo"
    }
    rows: list[dict[str, Any]] = []
    for raw in profile["symbols"]:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("source_symbol", "")).upper()
        if not symbol or symbol in reviewed or symbol in _DEFERRED_SYMBOLS:
            continue
        first_date = str(raw.get("first_date", ""))
        row_count = int(raw.get("row_count", 0))
        rows.append(
            {
                "source_symbol": symbol,
                "first_date": first_date,
                "last_date": str(raw.get("last_date", "")),
                "row_count": row_count,
                "split_event_count": int(raw.get("split_event_count", 0)),
                "dividend_event_count": int(raw.get("dividend_event_count", 0)),
                "triage_bucket": (
                    "CAMPAIGN_START_1996"
                    if first_date == "1996-01-02"
                    else "POST_CAMPAIGN_START"
                ),
            }
        )

    rows.sort(key=lambda item: _priority(item["first_date"], item["row_count"]))
    selected = rows[: args.limit]
    output_dir = root / "evidence" / "identity-review-queue"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "tiingo-unreviewed-durable.json"
    csv_path = output_dir / "tiingo-unreviewed-durable.csv"

    profile_symbol_count = int(profile.get("symbol_count", len(profile["symbols"])))
    json_path.write_text(
        json.dumps(
            {
                "schema_version": "tiingo-identity-review-queue-v0.1",
                "profile_symbol_count": profile_symbol_count,
                "reviewed_symbol_count": len(reviewed),
                "deferred_symbol_count": len(_DEFERRED_SYMBOLS),
                "unreviewed_durable_symbol_count": len(rows),
                "selected_count": len(selected),
                "selected_limit": args.limit,
                "symbols": selected,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "source_symbol",
            "first_date",
            "last_date",
            "row_count",
            "split_event_count",
            "dividend_event_count",
            "triage_bucket",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)

    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "csv_path": str(csv_path),
                "profile_symbol_count": profile_symbol_count,
                "reviewed_symbol_count": len(reviewed),
                "deferred_symbol_count": len(_DEFERRED_SYMBOLS),
                "unreviewed_durable_symbol_count": len(rows),
                "selected_count": len(selected),
                "campaign_start_selected_count": sum(
                    item["triage_bucket"] == "CAMPAIGN_START_1996" for item in selected
                ),
                "provider_calls_made": False,
                "identity_decisions_made": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
