"""Resolve remaining Tiingo identity boundaries using a broader SEC filing set."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.auto_identity_import import (
    AutoIdentityImportError,
    SecIdentityClient,
    load_sec_catalog,
)
from trade_scout.data.extended_identity_resolution import (
    ExtendedIdentityResolution,
    resolve_extended_sec_identity,
)


class ExtendedIdentityCommandError(RuntimeError):
    """Raised when extended Tiingo identity evidence cannot be processed safely."""


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
    if args.sleep < 0:
        parser.error("--sleep must be non-negative")

    root = args.root.expanduser().resolve()
    source_path = root / "evidence" / "deferred-resolution" / "remaining.json"
    output_root = root / "evidence" / "deferred-resolution" / "extended"
    output_root.mkdir(parents=True, exist_ok=True)
    ready_path = output_root / "ready.json"
    remaining_path = output_root / "remaining.json"
    summary_path = output_root / "summary.json"

    try:
        rows = _load_remaining(source_path)
        client = SecIdentityClient(
            user_agent=args.sec_user_agent,
            minimum_interval_seconds=args.sleep,
        )
        catalog = load_sec_catalog(client)

        resolutions: list[ExtendedIdentityResolution] = []
        passthrough: list[dict[str, object]] = []
        eligible_kinds = {
            "BOUNDARY_NOT_PROVEN",
            "CAMPAIGN_BOUNDARY_NOT_PROVEN",
            "POST_BOUNDARY_ONLY",
        }
        eligible = [row for row in rows if _text(row.get("resolution_kind")) in eligible_kinds]
        for row in rows:
            if _text(row.get("resolution_kind")) not in eligible_kinds:
                passthrough.append(row)

        for index, row in enumerate(eligible, start=1):
            symbol = _text(row.get("source_symbol")).upper()
            aliases = _aliases(symbol)
            companies = {catalog[key] for key in aliases if key in catalog}
            print(f"[{index}/{len(eligible)}] {symbol}: extended SEC evidence", flush=True)
            if len(companies) != 1:
                passthrough.append(row)
                print("    -> DEFERRED NO_UNIQUE_SEC_TICKER_MATCH", flush=True)
                continue
            company = next(iter(companies))
            row_cik = row.get("cik")
            if isinstance(row_cik, int) and row_cik > 0 and row_cik != company.cik:
                passthrough.append(row)
                print("    -> DEFERRED SEC_CIK_CHANGED", flush=True)
                continue
            resolution = resolve_extended_sec_identity(
                client=client,
                company=company,
                source_symbol=symbol,
                observed_first_date=date.fromisoformat(_text(row.get("observed_first_date"))),
            )
            resolutions.append(resolution)
            print(f"    -> {resolution.status} {resolution.resolution_kind}", flush=True)

        ready = [item for item in resolutions if item.ready]
        deferred = [item for item in resolutions if not item.ready]
        _write(ready_path, {"resolutions": [_json_resolution(item) for item in ready]})
        _write(
            remaining_path,
            {
                "resolutions": [
                    *[_json_resolution(item) for item in deferred],
                    *passthrough,
                ]
            },
        )
        summary = {
            "schema_version": "tiingo-extended-identity-resolution-v0.1",
            "source_count": len(rows),
            "attempted_count": len(eligible),
            "ready_count": len(ready),
            "remaining_count": len(deferred) + len(passthrough),
            "ready_kind_counts": dict(Counter(item.resolution_kind for item in ready)),
            "deferred_kind_counts": dict(Counter(item.resolution_kind for item in deferred)),
            "ready_path": str(ready_path),
            "remaining_path": str(remaining_path),
            "canonical_state_mutated": False,
            "provider_calls_made": False,
            "sec_calls_made": True,
            "status": "CHECK_COMPLETE",
        }
        _write(summary_path, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (AutoIdentityImportError, ExtendedIdentityCommandError, OSError, ValueError) as exc:
        print(f"extended Tiingo identity resolution error: {exc}", file=sys.stderr)
        return 2


def _load_remaining(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise ExtendedIdentityCommandError(f"remaining deferred evidence is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("resolutions"), list):
        raise ExtendedIdentityCommandError("remaining deferred evidence has unsupported structure")
    rows: list[dict[str, object]] = []
    for row in payload["resolutions"]:
        if not isinstance(row, dict):
            raise ExtendedIdentityCommandError("remaining deferred evidence contains malformed row")
        rows.append(row)
    return rows


def _json_resolution(item: ExtendedIdentityResolution) -> dict[str, object]:
    payload = asdict(item)
    payload["observed_first_date"] = item.observed_first_date.isoformat()
    return payload


def _aliases(symbol: str) -> tuple[str, ...]:
    result = {symbol}
    if "." in symbol:
        result.add(symbol.replace(".", "-"))
    if "-" in symbol:
        result.add(symbol.replace("-", "."))
    return tuple(sorted(result))


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtendedIdentityCommandError("required evidence field must be non-empty text")
    return value.strip()


def _write(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
