from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    PriceRepresentation,
    QualityStatus,
    SecurityType,
    SymbolHistoryRecord,
)
from trade_scout.data.instrument_storage import (
    InstrumentMasterPromotionRequest,
    InstrumentMasterStore,
)
from trade_scout.data.research_dataset import ResearchDatasetLoader
from trade_scout.data.serving import ResearchDataRequest
from trade_scout.universe.construction import UniverseMeasurementPolicy
from trade_scout.universe.eligibility import UniverseRules


def _instrument(instrument_id: str, *, delisting_date: date | None = None) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=instrument_id.upper(),
        name=instrument_id,
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=date(2020, 1, 2),
        delisting_date=delisting_date,
        provider_ids=MappingProxyType({"primary": instrument_id}),
    )


def _bar(instrument_id: str, trade_date: date, close: float) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=close,
        high_raw=close,
        low_raw=close,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close,
        low_split_adjusted=close,
        close_split_adjusted=close,
        provider_id="primary",
        dataset_version=DatasetVersion("equities-v1"),
        quality_status=QualityStatus.PASS,
    )


def _promote_foundation(root: Path) -> None:
    instruments = (
        _instrument("tsi-live"),
        _instrument("tsi-old", delisting_date=date(2020, 1, 3)),
    )
    history = tuple(
        SymbolHistoryRecord(
            instrument_id=instrument.instrument_id,
            symbol=instrument.primary_symbol,
            exchange=instrument.exchange,
            effective_from=date(2020, 1, 2),
            effective_to=instrument.delisting_date,
        )
        for instrument in instruments
    )
    InstrumentMasterStore(root).promote(
        instruments,
        history,
        InstrumentMasterPromotionRequest(
            snapshot_version="instrument-v1",
            primary_provider_id="primary",
            created_at=datetime(2026, 8, 9, tzinfo=UTC),
            source_batch_ids=("identity-batch-1",),
            identity_definition_version="identity-v1",
            symbol_history_definition_version="symbols-v1",
        ),
    )

    bars = (
        _bar("tsi-live", date(2020, 1, 2), 10.0),
        _bar("tsi-live", date(2020, 1, 3), 11.0),
        _bar("tsi-live", date(2020, 1, 6), 12.0),
        _bar("tsi-old", date(2020, 1, 2), 20.0),
        _bar("tsi-old", date(2020, 1, 3), 21.0),
    )
    CanonicalDailyBarStore(root).promote(
        bars,
        DatasetPromotionRequest(
            dataset_id="us-equities",
            dataset_version=DatasetVersion("equities-v1"),
            primary_provider_id="primary",
            created_at=datetime(2026, 8, 9, tzinfo=UTC),
            source_batch_ids=("bars-batch-1",),
            transformation_version="normalize-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="universe-v1",
            quality_check_version="quality-v1",
        ),
    )


def test_loader_reconstructs_point_in_time_eligibility_from_verified_stores(tmp_path: Path) -> None:
    _promote_foundation(tmp_path)

    result = ResearchDatasetLoader(tmp_path).load(
        instrument_snapshot_version="instrument-v1",
        request=ResearchDataRequest(
            dataset_version=DatasetVersion("equities-v1"),
            start=date(2020, 1, 2),
            end=date(2020, 1, 6),
            price_representation=PriceRepresentation.RAW,
            allowed_quality_states=frozenset({QualityStatus.PASS}),
        ),
        universe_rules=UniverseRules(
            version="universe-v1",
            allowed_exchanges=frozenset({"XNYS"}),
            allowed_security_types=frozenset({SecurityType.COMMON_STOCK}),
            allowed_quality_states=frozenset({QualityStatus.PASS}),
            min_price=5.0,
            min_avg_dollar_volume=5_000_000.0,
            min_trading_sessions=2,
        ),
        measurement_policy=UniverseMeasurementPolicy(
            version="measurements-v1",
            liquidity_lookback_sessions=2,
        ),
    )

    eligibility = {(str(row.instrument_id), row.trade_date): row.eligibility for row in result.rows}
    assert eligibility[("tsi-live", date(2020, 1, 2))] is False
    assert eligibility[("tsi-live", date(2020, 1, 3))] is True
    assert eligibility[("tsi-old", date(2020, 1, 3))] is True
    assert result.canonical_manifest.dataset_version == DatasetVersion("equities-v1")
    assert result.instrument_manifest.snapshot_version == "instrument-v1"
    assert result.universe_history.rules_version == "universe-v1"
