from datetime import UTC, date, datetime
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    CorporateActionRecord,
    CorporateActionType,
    InstrumentId,
    InstrumentRecord,
    SecurityType,
)
from trade_scout.data.corporate_action_storage import (
    CorporateActionDatasetConflictError,
    CorporateActionDatasetIntegrityError,
    CorporateActionPromotionRequest,
    CorporateActionStore,
)
from trade_scout.data.corporate_actions import (
    CorporateActionConflictError,
    normalize_provider_corporate_actions,
)
from trade_scout.data.provider import ProviderCorporateAction


def _instrument(
    instrument_id: str = "tsi_1",
    *,
    provider_instrument_id: str = "FIGI-1",
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol="AAA",
        name="AAA Corp",
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=date(2020, 1, 2),
        delisting_date=None,
        provider_ids=MappingProxyType({"massive": provider_instrument_id}),
    )


def _provider_action(
    *,
    provider_instrument_id: str = "FIGI-1",
    source_event_id: str | None = "event-1",
    action_type: CorporateActionType = CorporateActionType.SPLIT,
    effective_date: date = date(2024, 9, 12),
    source_fields: dict[str, str | int | float | bool | None] | None = None,
) -> ProviderCorporateAction:
    return ProviderCorporateAction(
        provider_id="massive",
        provider_instrument_id=provider_instrument_id,
        source_event_id=source_event_id,
        action_type=action_type,
        effective_date=effective_date,
        source_fields=source_fields or {"split_from": 1, "split_to": 4},
    )


def _request(version: str = "corporate-actions-v0.1.0") -> CorporateActionPromotionRequest:
    return CorporateActionPromotionRequest(
        dataset_version=version,
        primary_provider_id="massive",
        created_at=datetime(2026, 8, 8, 14, 30, tzinfo=UTC),
        source_batch_ids=("split-batch-1", "dividend-batch-1"),
        normalization_version="corporate-actions-v0.1.0",
        instrument_snapshot_version="instrument-master-v0.1.0",
    )


def test_normalization_resolves_only_exact_provider_identity() -> None:
    instruments = (_instrument(),)
    records = (
        _provider_action(),
        _provider_action(
            provider_instrument_id="UNKNOWN",
            source_event_id="event-2",
            action_type=CorporateActionType.CASH_DIVIDEND,
        ),
    )

    result = normalize_provider_corporate_actions(records, instruments)

    assert len(result.records) == 1
    assert result.records[0].instrument_id == InstrumentId("tsi_1")
    assert result.records[0].action_id.startswith("tca_")
    assert result.records[0].source_event_id == "event-1"
    assert len(result.unresolved) == 1
    assert result.unresolved[0].provider_instrument_id == "UNKNOWN"


def test_normalization_action_id_is_stable_without_ticker() -> None:
    instruments = (_instrument(),)
    first = normalize_provider_corporate_actions((_provider_action(),), instruments).records[0]
    second = normalize_provider_corporate_actions((_provider_action(),), instruments).records[0]

    assert first.action_id == second.action_id


def test_conflicting_provider_event_identity_is_rejected() -> None:
    instruments = (_instrument(),)

    with pytest.raises(CorporateActionConflictError, match="conflicting provider records"):
        normalize_provider_corporate_actions(
            (
                _provider_action(source_fields={"split_from": 1, "split_to": 4}),
                _provider_action(source_fields={"split_from": 1, "split_to": 5}),
            ),
            instruments,
        )


def test_promote_and_load_canonical_actions_round_trip(tmp_path) -> None:
    normalized = normalize_provider_corporate_actions(
        (
            _provider_action(),
            _provider_action(
                source_event_id="div-1",
                action_type=CorporateActionType.CASH_DIVIDEND,
                effective_date=date(2026, 5, 11),
                source_fields={"cash_amount": 0.26},
            ),
        ),
        (_instrument(),),
    )
    store = CorporateActionStore(tmp_path)

    manifest = store.promote(normalized.records, _request())
    loaded = store.load(manifest.dataset_version)

    assert manifest.record_count == 2
    assert manifest.first_effective_date == date(2024, 9, 12)
    assert manifest.last_effective_date == date(2026, 5, 11)
    assert loaded == normalized.records
    assert (tmp_path / manifest.parquet_relative_path).is_file()
    assert (tmp_path / "metadata" / "datasets.duckdb").is_file()


def test_empty_corporate_action_snapshot_is_supported(tmp_path) -> None:
    store = CorporateActionStore(tmp_path)

    manifest = store.promote((), _request())

    assert manifest.record_count == 0
    assert manifest.first_effective_date is None
    assert manifest.last_effective_date is None
    assert store.load(manifest.dataset_version) == ()


def test_identical_repromotion_is_idempotent(tmp_path) -> None:
    record = normalize_provider_corporate_actions(
        (_provider_action(),), (_instrument(),)
    ).records[0]
    store = CorporateActionStore(tmp_path)
    first = store.promote((record,), _request())

    second = store.promote((record,), _request())

    assert second == first


def test_version_reuse_with_changed_actions_is_rejected(tmp_path) -> None:
    record = normalize_provider_corporate_actions(
        (_provider_action(),), (_instrument(),)
    ).records[0]
    store = CorporateActionStore(tmp_path)
    store.promote((record,), _request())
    changed = CorporateActionRecord(
        action_id=record.action_id,
        instrument_id=record.instrument_id,
        action_type=record.action_type,
        effective_date=record.effective_date,
        provider_id=record.provider_id,
        source_event_id=record.source_event_id,
        source_fields=MappingProxyType({"split_from": 1, "split_to": 5}),
    )

    with pytest.raises(CorporateActionDatasetConflictError):
        store.promote((changed,), _request())


def test_promotion_rejects_non_primary_provider(tmp_path) -> None:
    record = CorporateActionRecord(
        action_id="tca_other",
        instrument_id=InstrumentId("tsi_1"),
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2024, 9, 12),
        provider_id="secondary",
        source_event_id="event-1",
        source_fields=MappingProxyType({"split_from": 1, "split_to": 4}),
    )

    with pytest.raises(CorporateActionDatasetIntegrityError, match="expected massive"):
        CorporateActionStore(tmp_path).promote((record,), _request())


def test_tampered_parquet_is_detected(tmp_path) -> None:
    record = normalize_provider_corporate_actions(
        (_provider_action(),), (_instrument(),)
    ).records[0]
    store = CorporateActionStore(tmp_path)
    manifest = store.promote((record,), _request())
    path = tmp_path / manifest.parquet_relative_path
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(CorporateActionDatasetIntegrityError, match="Parquet checksum"):
        store.load(manifest.dataset_version)
