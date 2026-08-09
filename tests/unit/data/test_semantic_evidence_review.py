from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.runtime_evidence import RuntimeEvidenceArtifact, RuntimeEvidenceRegistry
from trade_scout.data.semantic_evidence_review import review_semantic_runtime_evidence


def _write(path: Path, payload: object) -> str:
    encoded = json.dumps(payload).encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def test_verified_demonstrated_report_becomes_promotion_candidate(tmp_path: Path) -> None:
    report_path = tmp_path / "cross-provider.json"
    checksum = _write(
        report_path,
        {
            "evaluation_id": "alpha-tiingo-cross-validation-v0.1",
            "expected_case_count": 2,
            "completed_case_count": 2,
            "complete": True,
            "unresolved_discrepancy_count": 0,
            "representative_sample_accepted": True,
            "cases": [{}, {}],
        },
    )
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="cross-provider",
                criterion=DataFoundationCriterion.CROSS_PROVIDER_VALIDATION,
                path=Path("cross-provider.json"),
                sha256=checksum,
                producer="test",
            ),
        )
    )

    report = review_semantic_runtime_evidence(registry, evidence_root=tmp_path)

    assert report.has_invalid_evidence is False
    assert report.reviews[0].semantic_status is AcceptanceEvidenceStatus.DEMONSTRATED
    assert report.reviews[0].is_promotion_candidate is True


def test_verified_partial_report_is_not_promotion_candidate(tmp_path: Path) -> None:
    report_path = tmp_path / "storage.json"
    checksum = _write(
        report_path,
        {
            "dataset_version": "dataset-v1",
            "record_count": 100,
            "unique_instrument_count": 2,
            "first_trade_date": "2020-01-02",
            "last_trade_date": "2021-12-31",
            "parquet_bytes": 5000,
            "filtered_query_count": 20,
            "representative_sample_accepted": False,
        },
    )
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="storage",
                criterion=DataFoundationCriterion.STORAGE_BENCHMARK,
                path=Path("storage.json"),
                sha256=checksum,
                producer="test",
            ),
        )
    )

    review = review_semantic_runtime_evidence(registry, evidence_root=tmp_path).reviews[0]

    assert review.semantic_status is AcceptanceEvidenceStatus.PARTIAL
    assert review.is_promotion_candidate is False


def test_checksum_failure_blocks_semantic_assessment(tmp_path: Path) -> None:
    _write(tmp_path / "evidence.json", {"hello": "world"})
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="bad-checksum",
                criterion=DataFoundationCriterion.DELISTINGS,
                path=Path("evidence.json"),
                sha256="0" * 64,
                producer="test",
            ),
        )
    )

    report = review_semantic_runtime_evidence(registry, evidence_root=tmp_path)

    assert report.has_invalid_evidence is True
    assert report.reviews[0].semantic_status is None
    assert report.reviews[0].assessment_error is not None


def test_registered_criterion_mismatch_is_invalid(tmp_path: Path) -> None:
    report_path = tmp_path / "listing.json"
    checksum = _write(
        report_path,
        {
            "evaluation_id": "alpha-vantage-live-evaluation-v0.3",
            "progress": {"complete": True},
            "listing_snapshots": [{"as_of": "2014-07-10", "delisted_count": 10}],
        },
    )
    registry = RuntimeEvidenceRegistry(
        (
            RuntimeEvidenceArtifact(
                artifact_id="wrong-criterion",
                criterion=DataFoundationCriterion.HISTORICAL_INGESTION,
                path=Path("listing.json"),
                sha256=checksum,
                producer="test",
            ),
        )
    )

    review = review_semantic_runtime_evidence(registry, evidence_root=tmp_path).reviews[0]

    assert review.semantic_status is None
    assert review.assessment_error is not None
