import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    SecurityType,
    SymbolHistoryRecord,
)
from trade_scout.data.durable_raw_receipt import (
    create_durable_raw_receipt,
    persist_durable_raw_receipt,
)
from trade_scout.data.instrument_storage import (
    InstrumentMasterPromotionRequest,
    InstrumentMasterStore,
)
from trade_scout.data.providers.tiingo_canonical_promotion import (
    TiingoCanonicalPromotionError,
    persist_tiingo_canonical_promotion_report,
    promote_reviewed_tiingo_prices,
)
from trade_scout.data.raw_store import RawBatchStore
from trade_scout.data.reviewed_identity_snapshot import (
    ProviderSeriesLink,
    ReviewedIdentitySnapshotCandidate,
    persist_reviewed_identity_snapshot_candidate,
)

_SYNTHETIC_DATASET_VERSION = DatasetVersion("synthetic-reviewed-prices-v0.1")


def _candidate(
    *,
    history_start: date = date(2020, 1, 1),
    snapshot_version: str = "synthetic-reviewed-identity-v0.1",
) -> ReviewedIdentitySnapshotCandidate:
    instrument_id = InstrumentId("tsi_test_reviewed_001")
    instrument = InstrumentRecord(
        instrument_id=instrument_id,
        primary_symbol="TEST",
        name="Test Corp",
        exchange="XNAS",
        security_type=SecurityType.COMMON_STOCK,
        currency="USD",
        first_trade_date=None,
        delisting_date=None,
        provider_ids=MappingProxyType(
            {
                "trade_scout_review": "rir-test-001",
                "tiingo": "tiingo-series:rir-test-001",
            }
        ),
    )
    history = SymbolHistoryRecord(
        instrument_id=instrument_id,
        symbol="TEST",
        exchange="XNAS",
        effective_from=history_start,
        effective_to=None,
    )
    link = ProviderSeriesLink(
        instrument_id=instrument_id,
        review_id="rir-test-001",
        provider_id="tiingo",
        provider_series_id="tiingo-series:rir-test-001",
        query_symbol="TEST",
    )
    return ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version=snapshot_version,
        primary_provider_id="trade_scout_review",
        identity_definition_version="reviewed-permanent-identity-v0.1",
        symbol_history_definition_version="explicit-dated-symbol-history-v0.1",
        identity_seed_sha256="1" * 64,
        lineage_audit_sha256="2" * 64,
        instruments=(instrument,),
        symbol_history=(history,),
        provider_series_links=(link,),
        coverage_gaps=(),
        evidence_refs=(),
    )


def _rows(*, mismatched_adjusted: bool = False) -> list[dict[str, object]]:
    first_adj_open = 999.0 if mismatched_adjusted else 50.0
    return [
        {
            "date": "2020-01-02T00:00:00.000Z",
            "open": 100.0,
            "high": 104.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1000,
            "adjOpen": first_adj_open,
            "adjHigh": 52.0,
            "adjLow": 49.0,
            "adjClose": 51.0,
            "divCash": 0.0,
            "splitFactor": 1.0,
        },
        {
            "date": "2020-01-03T00:00:00.000Z",
            "open": 51.0,
            "high": 53.0,
            "low": 50.0,
            "close": 52.0,
            "volume": 2000,
            "adjOpen": 51.0,
            "adjHigh": 53.0,
            "adjLow": 50.0,
            "adjClose": 52.0,
            "divCash": 0.0,
            "splitFactor": 2.0,
        },
    ]


def _workspace_inputs(
    tmp_path: Path,
    *,
    candidate: ReviewedIdentitySnapshotCandidate,
    rows: list[dict[str, object]],
) -> tuple[Path, Path, Path, Path]:
    canonical_root = tmp_path / "canonical-store"
    raw_root = tmp_path / "providers" / "tiingo" / "raw"
    receipt_root = tmp_path / "providers" / "tiingo" / "receipts"
    candidate_path = tmp_path / "evidence" / "instrument-identity" / "candidate.json"
    persist_reviewed_identity_snapshot_candidate(candidate_path, candidate)

    InstrumentMasterStore(canonical_root).promote(
        candidate.instruments,
        candidate.symbol_history,
        InstrumentMasterPromotionRequest(
            snapshot_version=candidate.snapshot_version,
            primary_provider_id=candidate.primary_provider_id,
            created_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
            source_batch_ids=("review-seed:test",),
            identity_definition_version=candidate.identity_definition_version,
            symbol_history_definition_version=candidate.symbol_history_definition_version,
        ),
    )

    payload = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    record = RawBatchStore(raw_root).persist(
        payload,
        batch_id="tiingo-test-full-history",
        provider_id="tiingo",
        endpoint="/tiingo/daily/TEST/prices",
        retrieval_time=datetime(2026, 8, 10, 9, 1, tzinfo=UTC),
        request_parameters={"startDate": "2020-01-01", "endDate": "2020-01-03"},
        media_type="application/json",
    )
    receipt = create_durable_raw_receipt(
        record,
        durable_root=raw_root,
        storage_namespace="test-private-v1",
        subject_key="TEST",
    )
    persist_durable_raw_receipt(receipt_root / "TEST.json", receipt)
    return receipt_root, raw_root, candidate_path, canonical_root


def test_promotes_reviewed_split_only_slice_and_is_idempotent(tmp_path: Path) -> None:
    inputs = _workspace_inputs(tmp_path, candidate=_candidate(), rows=_rows())

    first = promote_reviewed_tiingo_prices(
        receipt_root=inputs[0],
        raw_root=inputs[1],
        storage_namespace="test-private-v1",
        candidate_path=inputs[2],
        canonical_root=inputs[3],
        dataset_version=_SYNTHETIC_DATASET_VERSION,
        promoted_at=datetime(2026, 8, 10, 9, 2, tzinfo=UTC),
    )
    second = promote_reviewed_tiingo_prices(
        receipt_root=inputs[0],
        raw_root=inputs[1],
        storage_namespace="test-private-v1",
        candidate_path=inputs[2],
        canonical_root=inputs[3],
        dataset_version=_SYNTHETIC_DATASET_VERSION,
    )

    assert first.already_registered is False
    assert second.already_registered is True
    assert first.manifest == second.manifest
    assert first.row_count == 2
    assert first.symbol_count == 1
    assert first.split_event_count == 1
    assert first.dividend_event_count == 0
    assert first.cross_check_eligible_symbol_count == 1
    assert first.cross_check_mismatch_field_count == 0
    assert first.manifest.quality_summary.pass_count == 2
    assert first.manifest.quality_summary.warn_count == 0
    assert first.manifest.primary_provider_id == "tiingo"
    assert first.manifest.universe_construction_version == "synthetic-reviewed-identity-v0.1"

    report_path = tmp_path / "promotion.json"
    persist_tiingo_canonical_promotion_report(report_path, first)
    report_text = report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["provider_acceptance_changed"] is False
    assert report["serving_selected"] is False
    assert report["record_count"] == 2
    assert "open_raw" not in report_text
    assert "close_split_adjusted" not in report_text


def test_expanded_identity_snapshot_maps_to_new_immutable_dataset_version(tmp_path: Path) -> None:
    candidate = _candidate(snapshot_version="tiingo-reviewed-identity-candidate-v0.3")
    inputs = _workspace_inputs(tmp_path, candidate=candidate, rows=_rows())

    result = promote_reviewed_tiingo_prices(
        receipt_root=inputs[0],
        raw_root=inputs[1],
        storage_namespace="test-private-v1",
        candidate_path=inputs[2],
        canonical_root=inputs[3],
    )

    assert str(result.manifest.dataset_version) == "tiingo-reviewed-split-only-v0.2"
    assert result.identity_snapshot_version == "tiingo-reviewed-identity-candidate-v0.3"


def test_unknown_identity_snapshot_requires_explicit_dataset_version(tmp_path: Path) -> None:
    inputs = _workspace_inputs(tmp_path, candidate=_candidate(), rows=_rows())

    with pytest.raises(TiingoCanonicalPromotionError, match="no approved canonical dataset version"):
        promote_reviewed_tiingo_prices(
            receipt_root=inputs[0],
            raw_root=inputs[1],
            storage_namespace="test-private-v1",
            candidate_path=inputs[2],
            canonical_root=inputs[3],
        )


def test_adjusted_cross_check_mismatch_blocks_promotion(tmp_path: Path) -> None:
    inputs = _workspace_inputs(
        tmp_path,
        candidate=_candidate(),
        rows=_rows(mismatched_adjusted=True),
    )

    with pytest.raises(TiingoCanonicalPromotionError, match="disagrees with eligible"):
        promote_reviewed_tiingo_prices(
            receipt_root=inputs[0],
            raw_root=inputs[1],
            storage_namespace="test-private-v1",
            candidate_path=inputs[2],
            canonical_root=inputs[3],
            dataset_version=_SYNTHETIC_DATASET_VERSION,
        )


def test_missing_dated_symbol_coverage_blocks_promotion(tmp_path: Path) -> None:
    inputs = _workspace_inputs(
        tmp_path,
        candidate=_candidate(history_start=date(2020, 1, 3)),
        rows=_rows(),
    )

    with pytest.raises(TiingoCanonicalPromotionError, match="normalization status"):
        promote_reviewed_tiingo_prices(
            receipt_root=inputs[0],
            raw_root=inputs[1],
            storage_namespace="test-private-v1",
            candidate_path=inputs[2],
            canonical_root=inputs[3],
            dataset_version=_SYNTHETIC_DATASET_VERSION,
        )
