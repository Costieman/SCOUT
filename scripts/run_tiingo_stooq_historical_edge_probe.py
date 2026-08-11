"""Probe the reviewed ALGN initial-history edge with no-credential Stooq evidence.

The probe keeps provider OHLCV in memory and publishes metadata-only evidence. Stooq CSV adjustment
semantics remain unaccepted, so even a corroborated edge is evidence for adjudication only and can
never trigger automatic canonical filling or promotion.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

from trade_scout.data.composite_evidence import CompositeCoverageState, build_composite_evidence
from trade_scout.data.contracts import InstrumentId, PriceRepresentation
from trade_scout.data.historical_edge import classify_initial_history_gap
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.stooq import StooqAdapter, StooqApiError, StooqInstrumentLink
from trade_scout.data.providers.tiingo import TiingoAdapter, TiingoApiError, TiingoInstrumentLink
from trade_scout.data.reconciliation import ReconciliationTolerance
from trade_scout.data.session_completeness import expected_exchange_sessions

_OUTPUT = Path("runtime/tiingo-stooq-historical-edge/report.json")
_TIINGO_SYMBOL = "ALGN"
_STOOQ_SYMBOL = "ALGN.US"
_EXCHANGE = "XNAS"
_LIFECYCLE_START = date(2001, 1, 26)
_TIINGO_OBSERVED_FIRST = date(2001, 1, 30)
_TIINGO_INSTRUMENT_ID = "tiingo-reviewed-algn-series"
_STOOQ_INSTRUMENT_ID = "stooq-reviewed-algn-us-series"
_TOLERANCE = ReconciliationTolerance(price_relative=1e-6, volume_relative=1e-6)


def main() -> int:
    tiingo_token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not tiingo_token:
        raise SystemExit("TIINGO_API_TOKEN is required")

    expected_gap_sessions = expected_exchange_sessions(
        exchange=_EXCHANGE,
        start=_LIFECYCLE_START,
        end=_TIINGO_OBSERVED_FIRST - timedelta(days=1),
    )
    expected_probe_sessions = (*expected_gap_sessions, _TIINGO_OBSERVED_FIRST)

    tiingo_request = DailyBarRequest(
        start=_LIFECYCLE_START,
        end=_TIINGO_OBSERVED_FIRST,
        provider_symbols=(_TIINGO_SYMBOL,),
        adjustment=PriceRepresentation.RAW,
        run_id="historical-edge:algn-2001:tiingo",
    )
    stooq_request = DailyBarRequest(
        start=_LIFECYCLE_START,
        end=_TIINGO_OBSERVED_FIRST,
        provider_symbols=(_STOOQ_SYMBOL,),
        adjustment=PriceRepresentation.RAW,
        run_id="historical-edge:algn-2001:stooq",
    )

    tiingo = TiingoAdapter.from_api_token(
        tiingo_token,
        instrument_links=(
            TiingoInstrumentLink(
                query_symbol=_TIINGO_SYMBOL,
                provider_instrument_id=_TIINGO_INSTRUMENT_ID,
            ),
        ),
    )
    try:
        tiingo_bars = tuple(tiingo.get_daily_bars(tiingo_request))
    except TiingoApiError as exc:
        _write_report(
            {
                "status": "INCONCLUSIVE_TIINGO_FAILURE",
                "provider_failure": {
                    "provider_id": "tiingo",
                    "error_type": type(exc).__name__,
                },
            },
            expected_gap_sessions=expected_gap_sessions,
        )
        return 0

    stooq = StooqAdapter.from_http(
        instrument_links=(
            StooqInstrumentLink(
                query_symbol=_STOOQ_SYMBOL,
                provider_instrument_id=_STOOQ_INSTRUMENT_ID,
            ),
        )
    )
    try:
        stooq_bars = tuple(stooq.get_daily_bars(stooq_request))
    except StooqApiError as exc:
        _write_report(
            {
                "status": "INCONCLUSIVE_STOOQ_FAILURE",
                "provider_failure": {
                    "provider_id": "stooq",
                    "error_type": type(exc).__name__,
                },
                "tiingo_observed_sessions": [bar.trade_date.isoformat() for bar in tiingo_bars],
            },
            expected_gap_sessions=expected_gap_sessions,
        )
        return 0

    evidence = build_composite_evidence(
        instrument_id=InstrumentId("reviewed-algn-historical-edge"),
        provider_a_id="tiingo",
        provider_a_instrument_id=_TIINGO_INSTRUMENT_ID,
        provider_a_bars=tiingo_bars,
        provider_b_id="stooq",
        provider_b_instrument_id=_STOOQ_INSTRUMENT_ID,
        provider_b_bars=stooq_bars,
        tolerance=_TOLERANCE,
    )
    expected_set = set(expected_probe_sessions)
    unexpected_dates = sorted({row.trade_date for row in evidence.rows} - expected_set)
    if unexpected_dates:
        raise RuntimeError(
            "provider returned observations outside the bounded historical-edge window"
        )

    status = classify_initial_history_gap(
        evidence,
        expected_gap_sessions=expected_gap_sessions,
        anchor_date=_TIINGO_OBSERVED_FIRST,
    )
    _write_report(
        {
            "status": str(status),
            "tiingo_observed_sessions": [bar.trade_date.isoformat() for bar in tiingo_bars],
            "stooq_observed_sessions": [bar.trade_date.isoformat() for bar in stooq_bars],
            "tiingo_only_sessions": [
                row.trade_date.isoformat()
                for row in evidence.rows
                if row.state is CompositeCoverageState.A_ONLY
            ],
            "stooq_only_sessions": [
                row.trade_date.isoformat()
                for row in evidence.rows
                if row.state is CompositeCoverageState.B_ONLY
            ],
            "agreement_sessions": [
                row.trade_date.isoformat()
                for row in evidence.rows
                if row.state is CompositeCoverageState.BOTH_AGREE
            ],
            "disagreement_sessions": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "fields": list(row.differing_fields),
                }
                for row in evidence.rows
                if row.state is CompositeCoverageState.BOTH_DISAGREE
            ],
        },
        expected_gap_sessions=expected_gap_sessions,
    )
    return 0


def _write_report(
    result: dict[str, object],
    *,
    expected_gap_sessions: tuple[date, ...],
) -> None:
    payload = {
        "schema_version": "tiingo-stooq-historical-edge-report-v0.1",
        "evaluation_id": "algn-2001-tiingo-stooq-initial-coverage-edge-v0.1",
        "tiingo_symbol": _TIINGO_SYMBOL,
        "stooq_symbol": _STOOQ_SYMBOL,
        "exchange": _EXCHANGE,
        "reviewed_lifecycle_start": _LIFECYCLE_START.isoformat(),
        "reviewed_tiingo_observed_first": _TIINGO_OBSERVED_FIRST.isoformat(),
        "expected_gap_sessions": [day.isoformat() for day in expected_gap_sessions],
        "anchor_date": _TIINGO_OBSERVED_FIRST.isoformat(),
        "stooq_adjustment_semantics_accepted": False,
        **result,
        "canonical_fill_allowed": False,
        "canonical_dataset_written": False,
        "provider_acceptance_changed": False,
        "serving_selected": False,
        "raw_provider_payload_uploaded": False,
        "price_rows_promoted": 0,
        "bars_fabricated": 0,
    }
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(_OUTPUT)


if __name__ == "__main__":
    raise SystemExit(main())
