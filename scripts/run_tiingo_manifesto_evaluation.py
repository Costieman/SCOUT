"""Run a credential-backed Tiingo evaluation against Trade Scout provider gates.

Only derived diagnostics and hashes are emitted. The API token and raw licensed
market-data rows are never written to the report.
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


def _rows(
    client: TiingoHttpClient,
    symbol: str,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    value = client.get_json(
        f"/tiingo/daily/{symbol}/prices",
        {"startDate": start, "endDate": end, "resampleFreq": "daily"},
    )
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"unexpected Tiingo price response for {symbol}")
    return value


def _metadata_gate(client: TiingoHttpClient) -> dict[str, object]:
    symbols = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM")
    summaries: list[dict[str, object]] = []
    passed = True
    for symbol in symbols:
        meta = client.get_json(f"/tiingo/daily/{symbol}")
        if not isinstance(meta, dict):
            passed = False
            summaries.append({"symbol": symbol, "shape": type(meta).__name__})
            continue
        required = {"ticker", "startDate", "endDate", "exchangeCode"}
        missing = sorted(required - set(meta))
        passed = passed and not missing
        summaries.append(
            {
                "symbol": symbol,
                "missing_fields": missing,
                "start_date": meta.get("startDate"),
                "end_date": meta.get("endDate"),
                "exchange_code": meta.get("exchangeCode"),
                "response_hash": _hash(meta),
            }
        )
    return _criterion(
        "reference_metadata_and_history_bounds",
        "PASS" if passed else "FAIL",
        {"symbols": summaries},
    )


def _history_gate(client: TiingoHttpClient) -> dict[str, object]:
    probes = (
        ("AAPL", "1996-01-02", "1996-01-12"),
        ("MSFT", "1996-01-02", "1996-01-12"),
        ("JPM", "1996-01-02", "1996-01-12"),
    )
    summaries: list[dict[str, object]] = []
    passed = True
    for symbol, start, end in probes:
        rows = _rows(client, symbol, start, end)
        passed = passed and bool(rows)
        summaries.append(
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
    return _criterion(
        "multi_decade_historical_depth",
        "PASS" if passed else "FAIL",
        {"probes": summaries},
    )


def _field_gate(client: TiingoHttpClient) -> dict[str, object]:
    summaries: list[dict[str, object]] = []
    passed = True
    for symbol in ("AAPL", "MSFT", "NVDA", "AMZN", "JPM"):
        rows = _rows(client, symbol, "2026-07-01", "2026-08-07")
        missing = (
            sorted(REQUIRED_PRICE_FIELDS - set(rows[0])) if rows else sorted(REQUIRED_PRICE_FIELDS)
        )
        passed = passed and bool(rows) and not missing
        summaries.append(
            {
                "symbol": symbol,
                "row_count": len(rows),
                "missing_required_fields": missing,
                "first_date": rows[0].get("date") if rows else None,
                "last_date": rows[-1].get("date") if rows else None,
                "response_hash": _hash(rows),
            }
        )
    return _criterion(
        "daily_ohlcv_adjustment_field_contract",
        "PASS" if passed else "FAIL",
        {"probes": summaries},
    )


def _corporate_action_gates(client: TiingoHttpClient) -> list[dict[str, object]]:
    split_rows = _rows(client, "AAPL", "2020-08-27", "2020-09-02")
    splits = [
        {"date": row.get("date"), "split_factor": row.get("splitFactor")}
        for row in split_rows
        if isinstance(row.get("splitFactor"), (int, float)) and float(row["splitFactor"]) != 1.0
    ]
    dividend_rows = _rows(client, "AAPL", "2024-01-01", "2024-12-31")
    dividends = [
        row.get("date")
        for row in dividend_rows
        if isinstance(row.get("divCash"), (int, float)) and float(row["divCash"]) != 0.0
    ]
    return [
        _criterion(
            "corporate_action_split_evidence",
            "PASS" if splits else "FAIL",
            {
                "event_count": len(splits),
                "events": splits,
                "response_hash": _hash(split_rows),
            },
        ),
        _criterion(
            "corporate_action_dividend_evidence",
            "PASS" if dividends else "FAIL",
            {
                "event_count": len(dividends),
                "event_dates": dividends,
                "response_hash": _hash(dividend_rows),
            },
        ),
    ]


def _determinism_gate(client: TiingoHttpClient) -> dict[str, object]:
    first = _rows(client, "AAPL", "2026-07-01", "2026-07-10")
    second = _rows(client, "AAPL", "2026-07-01", "2026-07-10")
    first_hash = _hash(first)
    second_hash = _hash(second)
    return _criterion(
        "repeat_request_determinism",
        "PASS" if first_hash == second_hash else "FAIL",
        {"first_hash": first_hash, "second_hash": second_hash, "row_count": len(first)},
    )


def _delisted_gate(client: TiingoHttpClient) -> dict[str, object]:
    try:
        meta = client.get_json("/tiingo/daily/TWTR")
        if not isinstance(meta, dict):
            return _criterion(
                "inactive_delisted_retrievability_probe",
                "FAIL",
                {"symbol": "TWTR", "response_type": type(meta).__name__},
            )
        return _criterion(
            "inactive_delisted_retrievability_probe",
            "PASS",
            {
                "symbol": "TWTR",
                "response_hash": _hash(meta),
                "start_date": meta.get("startDate"),
                "end_date": meta.get("endDate"),
            },
        )
    except Exception as exc:
        return _criterion(
            "inactive_delisted_retrievability_probe",
            "PARTIAL",
            {"symbol": "TWTR", "error_type": type(exc).__name__},
        )


def _static_gates() -> list[dict[str, object]]:
    return [
        _criterion(
            "secret_isolation",
            "PASS",
            {
                "mechanism": "environment_secret_and_Authorization_header",
                "token_logged": False,
            },
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
                "reason": (
                    "explicit identity links exist, but accepted dated symbol history "
                    "is not yet implemented"
                )
            },
        ),
        _criterion(
            "delisting_survivor_bias_characterization",
            "PARTIAL",
            {
                "reason": (
                    "one delisted-ticker probe cannot establish systematic inactive "
                    "coverage"
                )
            },
        ),
        _criterion(
            "rate_retry_checkpoint_backfill_behavior",
            "NOT_TESTED",
            {"reason": "the credential probe is below primary-provider backfill scale"},
        ),
        _criterion(
            "canonical_normalization",
            "BLOCKED",
            {
                "reason": (
                    "event splitFactor must be transformed into Trade Scout's cumulative "
                    "split-only multiplier"
                )
            },
        ),
        _criterion(
            "secondary_source_validation",
            "NOT_TESTED",
            {"reason": "representative cross-provider reconciliation remains required"},
        ),
    ]


def main() -> int:
    token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("TIINGO_API_TOKEN is not configured")

    client = TiingoHttpClient(token)
    health = client.get_json("/api/test/")
    criteria = [
        _criterion(
            "authentication_and_connectivity",
            "PASS" if isinstance(health, dict) else "FAIL",
            {"response_type": type(health).__name__, "response_hash": _hash(health)},
        ),
        _metadata_gate(client),
        _history_gate(client),
        _field_gate(client),
        *_corporate_action_gates(client),
        _determinism_gate(client),
        _delisted_gate(client),
        *_static_gates(),
    ]
    transport_gates = {
        "authentication_and_connectivity",
        "reference_metadata_and_history_bounds",
        "multi_decade_historical_depth",
        "daily_ohlcv_adjustment_field_contract",
    }
    failed_transport = any(
        item["status"] == "FAIL"
        for item in criteria
        if item["criterion"] in transport_gates
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
