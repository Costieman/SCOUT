from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.historical_evidence import (
    HistoricalEvidenceCase,
    HistoricalEvidenceState,
    evaluate_historical_ohlcv,
)
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    DataFamily,
    ProviderCapabilities,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInstrument,
    ProviderSymbolHistory,
)


class _Adapter:
    provider_id = "fixture"

    def __init__(
        self,
        bars: tuple[ProviderDailyBar, ...],
        *,
        second: tuple[ProviderDailyBar, ...] | None = None,
    ) -> None:
        self._bars = bars
        self._second = second
        self._calls = 0

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            data_families=frozenset({DataFamily.DAILY_BARS}),
            adjustment_modes=frozenset({PriceRepresentation.RAW}),
            earliest_daily_bar_date=None,
            supports_delisted=False,
            supports_symbol_history=False,
            timestamp_convention="fixture",
            known_limitations=(),
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        del as_of
        return ()

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        del provider_instrument_ids
        return ()

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        del request
        self._calls += 1
        if self._calls == 2 and self._second is not None:
            return self._second
        return self._bars

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        del request
        return ()


def _bar(day: int, *, symbol: str = "ABC", provider: str = "fixture") -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider,
        provider_instrument_id=f"{provider}:{symbol}",
        symbol=symbol,
        trade_date=date(2020, 1, day),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000_000.0,
    )


def _case() -> HistoricalEvidenceCase:
    return HistoricalEvidenceCase(
        case_id="abc-2020",
        provider_symbol="ABC",
        start=date(2020, 1, 1),
        end=date(2020, 1, 10),
        minimum_observations=3,
        max_start_lag_days=2,
        max_end_lag_days=3,
    )


def test_historical_evidence_passes_reproducible_scoped_sample() -> None:
    bars = (_bar(2), _bar(3), _bar(7))

    report = evaluate_historical_ohlcv(_Adapter(bars), (_case(),))

    assert report.provider_id == "fixture"
    assert report.passed is True
    result = report.cases[0]
    assert result.observation_count == 3
    assert result.first_trade_date == date(2020, 1, 2)
    assert result.last_trade_date == date(2020, 1, 7)
    assert all(check.state is HistoricalEvidenceState.PASS for check in result.checks)


def test_pacing_hook_runs_between_repeatability_requests() -> None:
    bars = (_bar(2), _bar(3), _bar(7))
    calls: list[str] = []

    evaluate_historical_ohlcv(_Adapter(bars), (_case(),), pace=lambda: calls.append("paced"))

    assert calls == ["paced"]


def test_repeatability_failure_is_visible() -> None:
    first = (_bar(2), _bar(3), _bar(7))
    second = (_bar(2), _bar(3), _bar(8))

    report = evaluate_historical_ohlcv(_Adapter(first, second=second), (_case(),))

    assert report.passed is False
    check = next(item for item in report.cases[0].checks if item.check_id == "repeatability")
    assert check.state is HistoricalEvidenceState.FAIL


def test_scope_duplicates_and_coverage_fail_without_repair() -> None:
    duplicate = _bar(5)
    bars = (
        duplicate,
        duplicate,
        _bar(6, symbol="OTHER"),
        _bar(7, provider="wrong"),
    )

    report = evaluate_historical_ohlcv(_Adapter(bars), (_case(),))

    states = {check.check_id: check.state for check in report.cases[0].checks}
    assert states["provider_scope"] is HistoricalEvidenceState.FAIL
    assert states["symbol_scope"] is HistoricalEvidenceState.FAIL
    assert states["unique_instrument_session"] is HistoricalEvidenceState.FAIL
    assert states["minimum_observations"] is HistoricalEvidenceState.PASS
    assert states["start_coverage"] is HistoricalEvidenceState.FAIL
    assert report.passed is False


def test_unsorted_provider_output_fails_deterministic_order_check() -> None:
    bars = (_bar(3), _bar(2), _bar(7))

    report = evaluate_historical_ohlcv(_Adapter(bars), (_case(),))

    check = next(item for item in report.cases[0].checks if item.check_id == "deterministic_order")
    assert check.state is HistoricalEvidenceState.FAIL


def test_cases_must_be_non_empty_and_unique() -> None:
    with pytest.raises(ValueError, match="at least one"):
        evaluate_historical_ohlcv(_Adapter(()), ())

    case = _case()
    with pytest.raises(ValueError, match="unique"):
        evaluate_historical_ohlcv(_Adapter(()), (case, case))
