from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import DatasetPromotionRequest
from trade_scout.data.composite_adjudication import CompositeAdjudicationState
from trade_scout.data.composite_dataset import (
    CompositeDatasetIntegrityError,
    CompositeDatasetStore,
)
from trade_scout.data.composite_evidence import CompositeCoverageState
from trade_scout.data.composite_promotion import (
    COMPOSITE_CANONICAL_PROVIDER_ID,
    CompositeCanonicalizationResult,
    CompositeRowProvenance,
)
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)


def _version() -> DatasetVersion:
    return DatasetVersion("ab-v0.1")


def _bar() -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId("instrument:spy"),
        trade_date=date(2026, 1, 2),
        open_raw=100.0,
        high_raw=101.0,
        low_raw=99.0,
        close_raw=100.5,
        volume_raw=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=None,
        high_split_adjusted=None,
        low_split_adjusted=None,
        close_split_adjusted=None,
        provider_id=COMPOSITE_CANONICAL_PROVIDER_ID,
        dataset_version=_version(),
        quality_status=QualityStatus.PASS,
    )


def _provenance() -> CompositeRowProvenance:
    return CompositeRowProvenance(
        instrument_id="instrument:spy",
        trade_date="2026-01-02",
        included=True,
        canonical_provider_id=COMPOSITE_CANONICAL_PROVIDER_ID,
        selected_source_provider_id="alpha_vantage",
        selected_source_provider_instrument_id="alpha_vantage:symbol:SPY",
        evidence_state=CompositeCoverageState.BOTH_AGREE,
        adjudication_state=CompositeAdjudicationState.CORROBORATED,
        review_note="A+B raw OHLCV agree within tolerance",
        corroborating_provider_ids=("alpha_vantage", "stooq"),
    )


def _request(*, provider_id: str = COMPOSITE_CANONICAL_PROVIDER_ID) -> DatasetPromotionRequest:
    return DatasetPromotionRequest(
        dataset_id="equities-daily-composite",
        dataset_version=_version(),
        primary_provider_id=provider_id,
        created_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        source_batch_ids=("alpha-batch", "stooq-batch"),
        transformation_version="ab-composite-v0.1",
        adjustment_policy_version="raw-v0.1",
        universe_construction_version="pit-v0.1",
        quality_check_version="quality-v0.1",
    )


def _result() -> CompositeCanonicalizationResult:
    return CompositeCanonicalizationResult(
        bars=(_bar(),),
        provenance=(_provenance(),),
        normalization_issues=(),
    )


def test_promote_then_load_verifies_canonical_and_provenance(tmp_path: Path) -> None:
    store = CompositeDatasetStore(tmp_path)
    manifest = store.promote(_result(), _request())
    loaded = store.load(_version())

    assert manifest == loaded.manifest
    assert loaded.bars == (_bar(),)
    assert loaded.provenance == (_provenance(),)


def test_promotion_requires_composite_dataset_identity(tmp_path: Path) -> None:
    store = CompositeDatasetStore(tmp_path)
    with pytest.raises(ValueError, match="composite provider identity"):
        store.promote(_result(), _request(provider_id="alpha_vantage"))


def test_load_fails_closed_when_only_provenance_exists(tmp_path: Path) -> None:
    store = CompositeDatasetStore(tmp_path)
    store._provenance.write(_version(), (_provenance(),))

    with pytest.raises(CompositeDatasetIntegrityError, match="incomplete canonical/provenance"):
        store.load(_version())
