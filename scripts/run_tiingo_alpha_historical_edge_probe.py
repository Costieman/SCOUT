"""Probe a reviewed Tiingo historical coverage edge with Alpha Vantage full-history evidence.

This GitHub-safe probe keeps provider payloads in memory and uploads derived metadata only. It does
not fill, interpolate, promote, or rewrite any historical bar.
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
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError
from trade_scout.data.providers.tiingo import TiingoAdapter, TiingoApiError, TiingoInstrumentLink
from trade_scout.data.reconciliation import ReconciliationTolerance
from trade_scout.data.session_completeness import expected_exchange_sessions

_OUTPUT = Path("runtime/tiingo-alpha-historical-edge/report.json")
_SYMBOL = "ALGN"
_EXCHANGE = "XNAS"
_LIFECYCLE_START = date(2001, 1, 26)
_TIINGO_OBSERVED_FIRST = date(2001, 1, 30)
_TOLERANCE = ReconciliationTolerance(price_relative=1e-6, volume_relative=1e-6)


def main() -> int:
    tiingo_token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not tiingo_token or not alpha_key:
        raise SystemExit("TIINGO_API_TOKEN and ALPHA_VANTAGE_API_KEY are required")

    expected_gap_sessions = expected_exchange_sessions(
        exchange=_EXCHANGE,
        start=_LIFECYCLE_START,
        end=_TIINGO_OBSERVED_FIRST - timedelta(days=1),
    )
    expected_probe_sessions = (*expected_gap_sessions, _TIINGO_OBSERVED_FIRST)
    request = DailyBarRequest(
        start=_LIFECYCLE_START,
        end=_TIINGO_OBSERVED_FIRST,
        provider_symbols=(_SYMBOL,),
        adjustment=PriceRepresentation.RAW,
        run_id="historical-edge:algn-2001-initial-coverage",
    )

    tiingo = TiingoAdapter.from_api_token(
        tiingo_token,
        instrument_links=(
            TiingoInstrumentLink(
                query_symbol=_SYMBOL,
                provider_instrument_id="tiingo-reviewed-algn-series",
            ),
        ),
    )
    try:
        tiingo_bars = tuple(tiingo.get_daily_bars(request))
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

    alpha = AlphaVantageAdapter.from_api_key(alpha_key, allow_full_history=True)
    try:
        alpha_bars = tuple(alpha.get_daily_bars(request))
    except AlphaVantageApiError as exc:
        _write_report(
            {
                "status": "INCONCLUSIVE_ALPHA_FULL_HISTORY_UNAVAILABLE",
                "provider_failure": {
                    "provider_id": "alpha_vantage",
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
        provider_a_instrument_id="tiingo-reviewed-algn-series",
        provider_a_bars=tiingo_bars,
        provider_b_id="alpha_vantage",
        provider_b_instrument_id="alpha_vantage:symbol:ALGN",
        provider_b_bars=alpha_bars,
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
            "alpha_vantage_observed_sessions": [bar.trade_date.isoformat() for bar in alpha_bars],
            "tiingo_only_sessions": [
                row.trade_date.isoformat()
                for row in evidence.rows
                if row.state is CompositeCoverageState.A_ONLY
            ],
            "alpha_vantage_only_sessions": [
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
        "schema_version": "tiingo-alpha-historical-edge-report-v0.1",
        "evaluation_id": "algn-2001-initial-coverage-edge-v0.1",
        "symbol": _SYMBOL,
        "exchange": _EXCHANGE,
        "reviewed_lifecycle_start": _LIFECYCLE_START.isoformat(),
        "reviewed_tiingo_observed_first": _TIINGO_OBSERVED_FIRST.isoformat(),
        "expected_gap_sessions": [day.isoformat() for day in expected_gap_sessions],
        "anchor_date": _TIINGO_OBSERVED_FIRST.isoformat(),
        "alpha_full_history_requested": True,
        "alpha_full_history_entitlement_assumed": False,
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
