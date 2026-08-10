"""Run a credential-backed Tiingo evaluation against Trade Scout provider gates.

The report contains only derived diagnostics and hashes, never the API token or raw
licensed market-data rows. A successful probe does not accept Tiingo as primary;
provider acceptance remains a separate reviewed decision.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from trade_scout.data.providers.tiingo import TiingoHttpClient

OUTPUT = Path("runtime/tiingo-manifesto-evaluation/report.json")
REQUIRED_PRICE_FIELDS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjOpen",
    "adjHigh",
    "adjLow",
    "adjClose",
    "divCash",
    "splitFactor",
}


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _criterion(name: str, status: str, evidence: dict[str, object]) -> dict[str, object]:
    return {"criterion": name, "status": status, "evidence": evidence}


def _rows(client: TiingoHttpClient, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    value = client.get_json(
        f"/tiingo/daily/{symbol}/prices",
        {"startDate": start, "endDate": end, "resampleFreq": "daily"},
    )
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"unexpected Tiingo price response for {symbol}")
    return value


def main() -> int:
    token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("TIINGO_API_TOKEN is not configured")

    client = TiingoHttpClient(token)
    criteria: list[dict[str, object]] = []

    health = client.get_json("/api/test/")
    criteria.append(
        _criterion(
            "authentication_and_connectivity",
            "PASS" if isinstance(health, dict) else "FAIL",
            {"response_type": type(health).__name__, "response_hash": _hash(health)},
        )
    )

    metadata_symbols = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM")
    metadata_summary: list[dict[str, object]] = []
    metadata_ok = True
    for symbol in metadata_symbols:
        meta = client.get_json(f"/tiingo/daily/{symbol}")
        if not isinstance(meta, dict):
            metadata_ok = False
            metadata_summary.append({"symbol": symbol, "shape": type(meta).__name__})
            continue
        required = {"ticker", "startDate", "endDate", "exchangeCode"}
        missing = sorted(required - set(meta))
        metadata_ok = metadata_ok and not missing
        metadata_summary.append(
            {
                "symbol": symbol,
                "missing_fields": missing,
                "start_date": meta.get("startDate"),
                "end_date": meta.get("endDate"),
                "exchange_code": meta.get("exchangeCode"),
                "response_hash": _hash(meta),
            }
        )
    criteria.append(
        _criterion(
            "reference_metadata_and_history_bounds",
            "PASS" if metadata_ok else "FAIL",
            {"symbols": metadata_summary},
        )
    )

    old_windows = (
        ("AAPL", "1996-01-02", "1996-01-12"),
        ("MSFT", "1996-01-02", "1996-01-12"),
        ("JPM", "1996-01-02", "1996-01-12"),
    )
    old_summary: list[dict[str, object]] = []
    old_ok = True
    for symbol, start, end in old_windows:
        rows = _rows(client, symbol, start, end)
        old_ok = old_ok and bool(rows)
        old_summary.append(
            {
                "symbol": symbol,
                "requested_start": start,
                "requested_end": end,
                "row_count": len(rows),
                "first_date": rows[0].get("date") if rows else None,
                "last_date": rows[-1].get("date") if rows else None,
                "response_hash": _hash(rows),
            }
        )
    criteria.append(
        _criterion(
            "multi_decade_historical_depth",
            "PASS" if old_ok else "FAIL",
            {"probes": old_summary},
        )
    )

    recent_symbols = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM")
    recent_summary: list[dict[str, object]] = []
    schema_ok = True
    for symbol in recent_symbols:
        rows = _rows(client, symbol, "2026-07-01", "2026-08-07")
        missing = (
            sorted(REQUIRED_PRICE_FIELDS - set(rows[0]))
            if rows
            else sorted(REQUIRED_PRICE_FIELDS)
        )
        schema_ok = schema_ok and bool(rows) and not missing
        recent_summary.append(
            {
                "symbol": symbol,
                "row_count": len(rows),
                "missing_required_fields": missing,
                "first_date": rows[0].get("date") if rows else None,
                "last_date": rows[-1].get("date") if rows else None,
                "response_hash": _hash(rows),
            }
        )
    criteria.append(
        _criterion(
            "daily_ohlcv_adjustment_field_contract",
            "PASS" if schema_ok else "FAIL",
            {"probes": recent_summary},
        )
    )

    split_rows = _rows(client, "AAPL", "2020-08-27", "2020-09-02")
    split_events = [
        {"date": row.get("date"), "split_factor": row.get("splitFactor")}
        for row in split_rows
        if isinstance(row.get("splitFactor"), (int, float)) and float(row["splitFactor"]) != 1.0
    ]
    criteria.append(
        _criterion(
            "corporate_action_split_evidence",
            "PASS" if split_events else "FAIL",
            {
                "event_count": len(split_events),
                "events": split_events,
                "response_hash": _hash(split_rows),
            },
        )
    )

    dividend_rows = _rows(client, "AAPL", "2024-01-01", "2024-12-31")
    dividend_dates = [
        row.get("date")
        for row in dividend_rows
        if isinstance(row.get("divCash"), (int, float)) and float(row["divCash"]) != 0.0
    ]
    criteria.append(
        _criterion(
            "corporate_action_dividend_evidence",
            "PASS" if dividend_dates else "FAIL",
            {
                "event_count": len(dividend_dates),
                "event_dates": dividend_dates,
                "response_hash": _hash(dividend_rows),
            },
        )
    )

    first = _rows(client, "AAPL", "2026-07-01", "2026-07-10")
    second = _rows(client, "AAPL", "2026-07-01", "2026-07-10")
    criteria.append(
        _criterion(
            "repeat_request_determinism",
            "PASS" if _hash(first) == _hash(second) else "FAIL",
            {"first_hash": _hash(first), "second_hash": _hash(second), "row_count": len(first)},
        )
    )

    delisted_meta: object
    try:
        delisted_meta = client.get_json("/tiingo/daily/TWTR")
        delisted_status = "PASS" if isinstance(delisted_meta, dict) else "FAIL"
        delisted_evidence = {
            "symbol": "TWTR",
            "response_type": type(delisted_meta).__name__,
            "response_hash": _hash(delisted_meta),
            "start_date": delisted_meta.get("startDate")
            if isinstance(delisted_meta, dict)
            else None,
            "end_date": delisted_meta.get("endDate")
            if isinstance(delisted_meta, dict)
            else None,
        }
    except Exception as exc:  # diagnostic boundary: preserve failure class, not token-bearing text
        delisted_status = "PARTIAL"
        delisted_evidence = {"symbol": "TWTR", "error_type": type(exc).__name__}
    criteria.append(
        _criterion("inactive_delisted_retrievability_probe", delisted_status, delisted_evidence)
    )

    # Static design gates established from the accepted Trade Scout specs and Tiingo license/docs.
    criteria.extend(
        [
            _criterion(
                "secret_isolation",
                "PASS",
                {"mechanism": "environment_secret_and_Authorization_header", "token_logged": False},
            ),
            _criterion(
                "licensing_and_raw_preservation",
                "PARTIAL",
                {
                    "starter_license": "internal_use_only",
                    "raw_payload_committed_or_uploaded": False,
                    "requires_review_before_any_redistribution": True,
                },
            ),
            _criterion(
                "stable_identifier_and_symbol_history",
                "BLOCKED",
                {
                    "reason": "current adapter requires explicit identity links and does not provide accepted dated symbol history"
                },
            ),
            _criterion(
                "delisting_survivor_bias_characterization",
                "PARTIAL",
                {
                    "reason": "single delisted-ticker probe is evidence only; systematic inactive coverage remains uncharacterized"
                },
            ),
            _criterion(
                "rate_retry_checkpoint_backfill_behavior",
                "NOT_TESTED",
                {
                    "reason": "small credential probe is intentionally below primary-provider acceptance scale"
                },
            ),
            _criterion(
                "canonical_normalization",
                "BLOCKED",
                {
                    "reason": "Tiingo EOD splitFactor is event-level while Trade Scout canonical split_factor expects a cumulative split-only multiplier"
                },
            ),
            _criterion(
                "secondary_source_validation",
                "NOT_TESTED",
                {
                    "reason": "cross-provider campaign follows only if Tiingo transport and field gates pass"
                },
            ),
        ]
    )

    failed_transport = any(
        item["status"] == "FAIL"
        for item in criteria
        if item["criterion"]
        in {
            "authentication_and_connectivity",
            "reference_metadata_and_history_bounds",
            "multi_decade_historical_depth",
            "daily_ohlcv_adjustment_field_contract",
        }
    )
    report = {
        "evaluation_id": "tiingo-manifesto-evaluation-v0.1",
        "run_date": date.today().isoformat(),
        "provider_id": "tiingo",
        "scope": "credential-backed primary-baseline candidate evaluation",
        "canonical_dataset_written": False,
        "raw_licensed_payload_uploaded": False,
        "transport_candidate_viable": not failed_transport,
        "primary_provider_accepted": False,
        "acceptance_state": "BLOCKED_PENDING_REQUIRED_GATES",
        "criteria": criteria,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 1 if failed_transport else 0


if __name__ == "__main__":
    raise SystemExit(main())
