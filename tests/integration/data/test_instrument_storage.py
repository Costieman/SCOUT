from datetime import UTC, date, datetime
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    InstrumentId,
    InstrumentRecord,
    SecurityType,
    SymbolHistoryRecord,
)
from trade_scout.data.instrument_storage import (
    InstrumentMasterConflictError,
    InstrumentMasterIntegrityError,
    InstrumentMasterPromotionRequest,
    InstrumentMasterStore,
)


def _instrument(
    instrument_id: str = "tsi_1",
    *,
    provider_id: str = "massive",
    provider_instrument_id: str = "FIGI-1",
    symbol: str = "AAA",
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=symbol,
        name=f"{symbol} Corp",
        exchange="XNYS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=date(2020, 1, 2),
        delisting_date=None,
        provider_ids=MappingProxyType({provider_id: provider_instrument_id}),
    )


def _history(
    instrument_id: str = "tsi_1",
    *,
    symbol: str = "AAA",
    start: date = date(2020, 1, 2),
    end: date | None = None,
) -> SymbolHistoryRecord:
    return SymbolHistoryRecord(
        instrument_id=InstrumentId(instrument_id),
        symbol=symbol,
        exchange="XNYS",
        effective_from=start,
        effective_to=end,
    )


def _request(version: str = "instrument-master-v0.1.0") -> InstrumentMasterPromotionRequest:
    return InstrumentMasterPromotionRequest(
        snapshot_version=version,
        primary_provider_id="massive",
        created_at=datetime(2026, 8, 8, 14, 0, tzinfo=UTC),
        source_batch_ids=("reference-batch-1", "symbol-batch-1"),
        identity_definition_version="identity-v0.1.0",
        symbol_history_definition_version="symbol-history-v0.1.0",
    )


def test_promote_and_load_round_trip(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)
    instruments = (
        _instrument("tsi_2", provider_instrument_id="FIGI-2", symbol="BBB"),
        _instrument(),
    )
    history = (
        _history("tsi_2", symbol="OLD", start=date(2020, 1, 2), end=date(2022, 6, 30)),
        _history("tsi_2", symbol="BBB", start=date(2022, 7, 1)),
        _history(),
    )

    manifest = store.promote(instruments, history, _request())
    snapshot = store.load(manifest.snapshot_version)

    assert manifest.instrument_count == 2
    assert manifest.symbol_history_count == 3
    assert snapshot.manifest == manifest
    assert [str(item.instrument_id) for item in snapshot.instruments] == ["tsi_1", "tsi_2"]
    assert snapshot.instruments[1].provider_ids == {"massive": "FIGI-2"}
    assert [item.symbol for item in snapshot.symbol_history] == ["AAA", "OLD", "BBB"]
    assert (tmp_path / manifest.instrument_parquet_relative_path).is_file()
    assert (tmp_path / manifest.symbol_history_parquet_relative_path).is_file()
    assert (tmp_path / "metadata" / "datasets.duckdb").is_file()


def test_identical_repromotion_is_idempotent(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)
    first = store.promote((_instrument(),), (_history(),), _request())

    second = store.promote((_instrument(),), (_history(),), _request())

    assert second == first


def test_snapshot_version_cannot_be_reused_for_changed_identity(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)
    store.promote((_instrument(),), (_history(),), _request())

    with pytest.raises(InstrumentMasterConflictError):
        store.promote(
            (_instrument(provider_instrument_id="FIGI-CHANGED"),),
            (_history(),),
            _request(),
        )


def test_provider_identity_cannot_map_to_two_instruments(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)

    with pytest.raises(InstrumentMasterIntegrityError, match="maps to multiple instruments"):
        store.promote(
            (
                _instrument("tsi_1", provider_instrument_id="FIGI-SAME"),
                _instrument("tsi_2", provider_instrument_id="FIGI-SAME", symbol="BBB"),
            ),
            (),
            _request(),
        )


def test_symbol_history_must_reference_known_instrument(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)

    with pytest.raises(InstrumentMasterIntegrityError, match="unknown instrument"):
        store.promote(
            (_instrument(),),
            (_history("tsi_missing"),),
            _request(),
        )


def test_overlapping_symbol_history_is_rejected(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)

    with pytest.raises(InstrumentMasterIntegrityError, match="overlapping"):
        store.promote(
            (_instrument(),),
            (
                _history(start=date(2020, 1, 2), end=date(2022, 12, 31)),
                _history(symbol="NEW", start=date(2022, 12, 31)),
            ),
            _request(),
        )


def test_primary_provider_identity_is_required(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)
    instrument = _instrument(provider_id="secondary", provider_instrument_id="OTHER-1")

    with pytest.raises(InstrumentMasterIntegrityError, match="lacks primary-provider identity"):
        store.promote((instrument,), (), _request())


def test_tampered_instrument_parquet_is_detected(tmp_path) -> None:
    store = InstrumentMasterStore(tmp_path)
    manifest = store.promote((_instrument(),), (_history(),), _request())
    path = tmp_path / manifest.instrument_parquet_relative_path
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(InstrumentMasterIntegrityError, match="Parquet checksum"):
        store.load(manifest.snapshot_version)
