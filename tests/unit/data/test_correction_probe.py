from collections.abc import Sequence
from dataclasses import replace
from datetime import date

import pytest

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.correction_probe import (
    CorrectionComparisonState,
    CorrectionProbeScopeError,
    capture_daily_bar_correction_snapshot,
    compare_daily_bar_correction_snapshots,
)
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    ProviderCapabilities,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderInstrument,
    ProviderSymbolHistory,
)


class SnapshotProvider:
    provider_id = "candidate"

    def __init__(self, bars: Sequence[ProviderDailyBar]) -> None:
        self.bars = tuple(bars)

    def describe_capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def health_check(self) -> ProviderHealth:
        raise NotImplementedError

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        raise NotImplementedError

    def get_symbol_history(
        self, *, provider_instrument_ids: Sequence[str] | None = None
    ) -> Sequence[ProviderSymbolHistory]:
        raise NotImplementedError

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        return self.bars

    def get_corporate_actions(
        self, request: CorporateActionRequest
    ) -> Sequence[ProviderCorporateAction]:
        raise NotImplementedError


def _bar(**overrides: object) -> ProviderDailyBar:
    values: dict[str, object] = {
        "provider_id": "candidate",
        "provider_instrument_id": "asset-1",
        "symbol": "AAA",
        "trade_date": date(2026, 6, 15),
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1_000_000.375,
        "split_factor": 1.0,
        "dividend_cash": 0.0,
        "adjusted_open": 100.0,
        "adjusted_high": 102.0,
        "adjusted_low": 99.0,
        "adjusted_close": 101.0,
    }
    values.update(overrides)
    return ProviderDailyBar(**values)  # type: ignore[arg-type]


def _request(**overrides: object) -> DailyBarRequest:
    values: dict[str, object] = {
        "start": date(2026, 6, 15),
        "end": date(2026, 6, 18),
        "provider_symbols": ("AAA",),
        "adjustment": PriceRepresentation.RAW,
        "run_id": "correction-probe:test",
    }
    values.update(overrides)
    return DailyBarRequest(**values)  # type: ignore[arg-type]


def test_snapshot_is_order_independent_and_preserves_fractional_volume() -> None:
    first = _bar()
    second = _bar(
        trade_date=date(2026, 6, 16),
        open=101.0,
        high=103.0,
        low=100.0,
        close=102.0,
        volume=999_999.625,
        adjusted_open=101.0,
        adjusted_high=103.0,
        adjusted_low=100.0,
        adjusted_close=102.0,
    )

    snapshot_a = capture_daily_bar_correction_snapshot(
        SnapshotProvider((first, second)),
        _request(),
    )
    snapshot_b = capture_daily_bar_correction_snapshot(
        SnapshotProvider((second, first)),
        _request(),
    )

    assert snapshot_a.logical_sha256 == snapshot_b.logical_sha256
    assert snapshot_a.record_count == 2


def test_snapshot_change_is_reported_as_revision() -> None:
    baseline = capture_daily_bar_correction_snapshot(
        SnapshotProvider((_bar(),)),
        _request(),
    )
    current = capture_daily_bar_correction_snapshot(
        SnapshotProvider((_bar(close=101.01),)),
        _request(),
    )

    comparison = compare_daily_bar_correction_snapshots(baseline, current)

    assert comparison.state is CorrectionComparisonState.REVISED
    assert comparison.baseline_sha256 != comparison.current_sha256


def test_identical_snapshots_compare_identically() -> None:
    baseline = capture_daily_bar_correction_snapshot(
        SnapshotProvider((_bar(),)),
        _request(),
    )

    comparison = compare_daily_bar_correction_snapshots(baseline, baseline)

    assert comparison.state is CorrectionComparisonState.IDENTICAL


def test_different_request_scope_is_not_comparable() -> None:
    baseline = capture_daily_bar_correction_snapshot(
        SnapshotProvider((_bar(),)),
        _request(),
    )
    current = replace(baseline, end="2026-06-19")

    comparison = compare_daily_bar_correction_snapshots(baseline, current)

    assert comparison.state is CorrectionComparisonState.NOT_COMPARABLE


def test_probe_rejects_out_of_scope_and_duplicate_records() -> None:
    with pytest.raises(CorrectionProbeScopeError, match="outside"):
        capture_daily_bar_correction_snapshot(
            SnapshotProvider((_bar(trade_date=date(2026, 6, 14)),)),
            _request(),
        )

    with pytest.raises(CorrectionProbeScopeError, match="duplicate"):
        capture_daily_bar_correction_snapshot(
            SnapshotProvider((_bar(), _bar())),
            _request(),
        )
