"""Diagnose the bounded Stooq ALGN historical request without publishing OHLCV."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.stooq import StooqAdapter, StooqApiError, StooqInstrumentLink

_OUTPUT = Path("runtime/stooq-historical-transport-diagnostic/report.json")
_SYMBOL = "ALGN.US"
_PROVIDER_INSTRUMENT_ID = "stooq-reviewed-algn-us-series"
_START = date(2001, 1, 26)
_END = date(2001, 1, 30)


def main() -> int:
    adapter = StooqAdapter.from_http(
        instrument_links=(
            StooqInstrumentLink(
                query_symbol=_SYMBOL,
                provider_instrument_id=_PROVIDER_INSTRUMENT_ID,
            ),
        )
    )
    request = DailyBarRequest(
        start=_START,
        end=_END,
        provider_symbols=(_SYMBOL,),
        adjustment=PriceRepresentation.RAW,
        run_id="diagnostic:stooq:algn-2001",
    )

    payload: dict[str, object] = {
        "schema_version": "stooq-historical-transport-diagnostic-v0.1",
        "symbol": _SYMBOL,
        "start": _START.isoformat(),
        "end": _END.isoformat(),
        "raw_provider_payload_uploaded": False,
        "canonical_dataset_written": False,
        "canonical_fill_allowed": False,
    }
    try:
        bars = tuple(adapter.get_daily_bars(request))
    except StooqApiError as exc:
        payload.update(
            {
                "status": "STOOQ_REQUEST_FAILED",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            }
        )
    else:
        payload.update(
            {
                "status": "STOOQ_REQUEST_SUCCEEDED",
                "observed_session_count": len(bars),
                "observed_sessions": [bar.trade_date.isoformat() for bar in bars],
            }
        )

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(_OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
