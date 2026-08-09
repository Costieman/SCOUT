from __future__ import annotations

from datetime import date

from trade_scout.data.historical_evidence import (
    HistoricalEvidenceCase,
    HistoricalEvidenceState,
    evaluate_historical_ohlcv,
)
from trade_scout.data.providers.stooq import StooqAdapter, StooqInstrumentLink


class SequenceStooqClient:
    def __init__(self, payloads: list[bytes]) -> None:
        self._payloads = list(payloads)

    def get_csv(self, *, symbol: str, start: date, end: date) -> bytes:
        del symbol, start, end
        if len(self._payloads) > 1:
            return self._payloads.pop(0)
        return self._payloads[0]


def _case() -> HistoricalEvidenceCase:
    return HistoricalEvidenceCase(
        case_id="aapl-bounded-history",
        provider_symbol="AAPL.US",
        start=date(2026, 8, 3),
        end=date(2026, 8, 7),
        minimum_observations=5,
        max_start_lag_days=0,
        max_end_lag_days=0,
    )


def _adapter(client: SequenceStooqClient) -> StooqAdapter:
    return StooqAdapter(
        client,
        instrument_links=(
            StooqInstrumentLink(
                query_symbol="AAPL.US",
                provider_instrument_id="evidence:aapl-us",
            ),
        ),
    )


def test_stooq_can_use_provider_neutral_historical_evidence_checks() -> None:
    payload = (
        b"Date,Open,High,Low,Close,Volume\n"
        b"2026-08-03,100,102,99,101,1000\n"
        b"2026-08-04,101,103,100,102,1100\n"
        b"2026-08-05,102,104,101,103,1200\n"
        b"2026-08-06,103,105,102,104,1300\n"
        b"2026-08-07,104,106,103,105,1400\n"
    )
    report = evaluate_historical_ohlcv(_adapter(SequenceStooqClient([payload])), (_case(),))

    assert report.provider_id == "stooq"
    assert report.passed is True
    assert report.cases[0].observation_count == 5
    assert all(check.state is HistoricalEvidenceState.PASS for check in report.cases[0].checks)


def test_stooq_repeatability_changes_remain_failed_evidence() -> None:
    first = (
        b"Date,Open,High,Low,Close,Volume\n"
        b"2026-08-03,100,102,99,101,1000\n"
        b"2026-08-04,101,103,100,102,1100\n"
        b"2026-08-05,102,104,101,103,1200\n"
        b"2026-08-06,103,105,102,104,1300\n"
        b"2026-08-07,104,106,103,105,1400\n"
    )
    revised = first.replace(b"104,106,103,105,1400", b"104,106,103,105.5,1400")
    report = evaluate_historical_ohlcv(
        _adapter(SequenceStooqClient([first, revised])),
        (_case(),),
    )

    repeatability = next(
        check for check in report.cases[0].checks if check.check_id == "repeatability"
    )
    assert repeatability.state is HistoricalEvidenceState.FAIL
    assert report.passed is False
