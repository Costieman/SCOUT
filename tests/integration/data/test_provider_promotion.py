from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion, InstrumentRecord, SecurityType
from trade_scout.data.instrument_master import instrument_from_primary_provider
from trade_scout.data.provider import ProviderDailyBar, ProviderInstrument
from trade_scout.data.provider_promotion import (
    ProviderPromotionError,
    ProviderPromotionResult,
    promote_provider_daily_bar_evaluation,
)


def _instrument(provider_instrument_id: str = "fixture:ABC") -> InstrumentRecord:
    return instrument_from_primary_provider(
        ProviderInstrument(
            provider_id="fixture",
            provider_instrument_id=provider_instrument_id,
            symbol="ABC",
            name="ABC Corp",
            exchange="NASDAQ",
            security_type=SecurityType.COMMON_STOCK,
            currency="USD",
            active=True,
            first_trade_date=date(2020, 1, 2),
            end_date=None,
            source_fields={},
        )
    )


def _bar(*, high: float = 11.0, low: float = 9.0) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id="fixture",
        provider_instrument_id="fixture:ABC",
        symbol="ABC",
        trade_date=date(2020, 1, 2),
        open=10.0,
        high=high,
        low=low,
        close=10.5,
        volume=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        adjusted_open=10.0,
        adjusted_high=high,
        adjusted_low=low,
        adjusted_close=10.5,
    )


def _promote(
    tmp_path: Path,
    bars: tuple[ProviderDailyBar, ...],
    *,
    instruments: tuple[InstrumentRecord, ...] | None = None,
    batches: tuple[str, ...] = ("raw-1",),
) -> ProviderPromotionResult:
    return promote_provider_daily_bar_evaluation(
        bars,
        instruments=(_instrument(),) if instruments is None else instruments,
        store=CanonicalDailyBarStore(tmp_path / "canonical-store"),
        dataset_id="provider-evaluation",
        dataset_version=DatasetVersion("provider-evaluation-v1"),
        primary_provider_id="fixture",
        source_batch_ids=batches,
        created_at=datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
        transformation_version="normalization-v1",
        adjustment_policy_version="split-only-v1",
        universe_construction_version="evaluation-scope-v1",
        quality_check_version="quality-v1",
    )


def test_promotes_only_after_normalization_and_preserves_raw_batch_provenance(
    tmp_path: Path,
) -> None:
    result = _promote(tmp_path, (_bar(),), batches=("raw-1", "raw-2"))

    assert result.normalization.normalization_issues == ()
    assert result.manifest.record_count == 1
    assert result.manifest.source_batch_ids == ("raw-1", "raw-2")
    assert result.manifest.primary_provider_id == "fixture"


def test_rejects_promotion_without_raw_source_batch_ids(tmp_path: Path) -> None:
    with pytest.raises(ProviderPromotionError, match="raw source batch IDs"):
        _promote(tmp_path, (_bar(),), batches=())


def test_unresolved_provider_identity_blocks_promotion(tmp_path: Path) -> None:
    with pytest.raises(ProviderPromotionError, match="normalization issues"):
        _promote(tmp_path, (_bar(),), instruments=(_instrument("fixture:OTHER"),))


def test_quarantined_quality_evidence_blocks_promotion(tmp_path: Path) -> None:
    with pytest.raises(ProviderPromotionError, match="quarantined or rejected"):
        _promote(tmp_path, (_bar(high=8.0, low=9.0),))


def test_declared_primary_provider_must_match_all_bars(tmp_path: Path) -> None:
    foreign = ProviderDailyBar(
        provider_id="other",
        provider_instrument_id="other:ABC",
        symbol="ABC",
        trade_date=date(2020, 1, 2),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        adjusted_open=10.0,
        adjusted_high=11.0,
        adjusted_low=9.0,
        adjusted_close=10.5,
    )

    with pytest.raises(ProviderPromotionError, match="declared primary provider"):
        _promote(tmp_path, (foreign,))
