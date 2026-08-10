"""Compare a tiny raw-OHLCV sample from Tiingo and Alpha Vantage.

This is an evaluation probe, not canonical reconciliation. It compares provider observations by
query symbol and trading date only, emits derived discrepancy metrics, and stops before spending
Alpha Vantage quota when Tiingo is throttled.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter
from trade_scout.data.providers.tiingo import TiingoHttpClient

OUTPUT = Path("runtime/tiingo-alpha-cross-validation/report.json")
SYMBOLS = ("AAPL", "JPM", "MSFT")
START = date(2026, 7, 1)
END = date(2026, 8, 7)
PRICE_REL_TOLERANCE = 1e-6
VOLUME_REL_TOLERANCE = 1e-6


def main() -> int:
    tiingo_token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not tiingo_token or not alpha_key:
        raise SystemExit("TIINGO_API_TOKEN and ALPHA_VANTAGE_API_KEY are required")

    tiingo = TiingoHttpClient(tiingo_token)
    alpha = AlphaVantageAdapter.from_api_key(alpha_key)
    cases: list[dict[str, object]] = []
    status = "COMPLETED"

    for symbol in SYMBOLS:
        try:
            tiingo_rows = _tiingo_rows(tiingo, symbol)
        except Exception as exc:
            if _is_http_429(exc):
                cases.append({"symbol": symbol, "status": "TIINGO_RATE_LIMITED"})
                status = "PAUSED_RATE_LIMITED"
                break
            cases.append(
                {
                    "symbol": symbol,
                    "status": "TIINGO_ERROR",
                    "error_type": type(exc).__name__,
                }
            )
            status = "STOPPED_ERROR"
            break

        try:
            alpha_bars = alpha.get_daily_bars(
                DailyBarRequest(
                    start=START,
                    end=END,
                    provider_symbols=(symbol,),
                    adjustment=PriceRepresentation.RAW,
                )
            )
        except Exception as exc:
            cases.append(
                {
                    "symbol": symbol,
                    "status": "ALPHA_VANTAGE_ERROR",
                    "error_type": type(exc).__name__,
                }
            )
            status = "STOPPED_ERROR"
            break

        alpha_rows = {
            bar.trade_date.isoformat(): {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in alpha_bars
        }
        cases.append(_compare(symbol, tiingo_rows, alpha_rows))

    report = {
        "evaluation_id": "tiingo-alpha-cross-validation-v0.1",
        "status": status,
        "symbols_requested": list(SYMBOLS),
        "start": START.isoformat(),
        "end": END.isoformat(),
        "canonical_dataset_written": False,
        "raw_provider_payload_uploaded": False,
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 1 if status == "STOPPED_ERROR" else 0


def _tiingo_rows(client: TiingoHttpClient, symbol: str) -> dict[str, dict[str, float]]:
    response = client.get_json(
        f"/tiingo/daily/{symbol}/prices",
        {
            "startDate": START.isoformat(),
            "endDate": END.isoformat(),
            "resampleFreq": "daily",
        },
    )
    if not isinstance(response, list):
        raise RuntimeError("Tiingo price response is not a list")
    result: dict[str, dict[str, float]] = {}
    for item in response:
        if not isinstance(item, dict):
            raise RuntimeError("Tiingo price row is not an object")
        raw_date = item.get("date")
        if not isinstance(raw_date, str):
            raise RuntimeError("Tiingo price row lacks a date")
        result[raw_date[:10]] = {
            field: _number(item.get(field), field)
            for field in ("open", "high", "low", "close", "volume")
        }
    return result


def _compare(
    symbol: str,
    tiingo: dict[str, dict[str, float]],
    alpha: dict[str, dict[str, float]],
) -> dict[str, object]:
    common = sorted(set(tiingo) & set(alpha))
    only_tiingo = sorted(set(tiingo) - set(alpha))
    only_alpha = sorted(set(alpha) - set(tiingo))
    max_relative: dict[str, float] = {}
    mismatch_count: dict[str, int] = {}
    for field in ("open", "high", "low", "close", "volume"):
        differences = [_relative_difference(tiingo[item][field], alpha[item][field]) for item in common]
        max_relative[field] = max(differences, default=0.0)
        tolerance = VOLUME_REL_TOLERANCE if field == "volume" else PRICE_REL_TOLERANCE
        mismatch_count[field] = sum(value > tolerance for value in differences)
    return {
        "symbol": symbol,
        "status": "COMPARED",
        "tiingo_row_count": len(tiingo),
        "alpha_vantage_row_count": len(alpha),
        "common_session_count": len(common),
        "tiingo_only_session_count": len(only_tiingo),
        "alpha_only_session_count": len(only_alpha),
        "max_relative_difference": max_relative,
        "mismatch_count": mismatch_count,
    }


def _relative_difference(left: float, right: float) -> float:
    denominator = max(abs(left), abs(right), 1e-12)
    return abs(left - right) / denominator


def _number(value: object, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise RuntimeError(f"Tiingo field {field} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"Tiingo field {field} is not finite")
    return number


def _is_http_429(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, HTTPError) and current.code == 429:
            return True
        current = current.__cause__ or current.__context__
    return False


if __name__ == "__main__":
    raise SystemExit(main())
