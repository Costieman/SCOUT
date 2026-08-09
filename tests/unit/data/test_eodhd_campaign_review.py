from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.provider_acceptance import (
    ProviderAcceptanceCriterion,
    ProviderEvidenceStatus,
)
from trade_scout.data.providers.eodhd_campaign_review import (
    EodhdCampaignReviewError,
    review_eodhd_campaign,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _case(
    case_id: str,
    symbol: str,
    *,
    active: bool,
    dataset_version: str,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "symbol": symbol,
        "start": "2020-01-02",
        "end": "2020-12-31",
        "expected_active": active,
        "dataset_version": dataset_version,
    }


def _result(
    case_id: str,
    symbol: str,
    *,
    state: str,
    dataset_version: str,
    actions: int = 0,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "symbol": symbol,
        "provider_instrument_id": f"isin:{case_id}",
        "expected_state": state,
        "requested_start": "2020-01-02",
        "requested_end": "2020-12-31",
        "bar_count": 250,
        "action_count": actions,
        "split_count": actions,
        "dividend_count": 0,
        "raw_batch_ids": [f"raw-{case_id}"],
        "dataset_version": dataset_version,
        "canonical_record_count": 250,
        "canonical_first_trade_date": "2020-01-02",
        "canonical_last_trade_date": "2020-12-31",
        "canonical_content_checksum_sha256": "a" * 64,
        "canonical_parquet_checksum_sha256": "b" * 64,
    }


def _build_campaign(root: Path, *, complete: bool = True) -> None:
    campaign_id = "eodhd-campaign-test"
    cases = [
        _case("active", "AAA.US", active=True, dataset_version="aaa-v1"),
        _case("delisted", "OLD.US", active=False, dataset_version="old-v1"),
    ]
    completed = ["active", "delisted"] if complete else ["active"]
    _write(
        root / "report" / campaign_id / "campaign-summary.json",
        {
            "evaluation_id": "eodhd-provider-evidence-campaign-v0.1",
            "provider_id": "eodhd",
            "campaign_id": campaign_id,
            "expected_case_count": 2,
            "completed_case_ids": completed,
            "complete": complete,
        },
    )
    _write(
        root / "campaign-state" / campaign_id / "campaign.json",
        {
            "schema_version": "eodhd-campaign-suite-v0.1",
            "campaign_id": campaign_id,
            "cases": cases,
        },
    )
    _write(
        root / "campaign-state" / campaign_id / "cases" / "active" / "result.json",
        _result("active", "AAA.US", state="active", dataset_version="aaa-v1", actions=1),
    )
    if complete:
        _write(
            root / "campaign-state" / campaign_id / "cases" / "delisted" / "result.json",
            _result("delisted", "OLD.US", state="delisted", dataset_version="old-v1"),
        )


def test_complete_campaign_demonstrates_only_directly_exercised_criteria(tmp_path: Path) -> None:
    _build_campaign(tmp_path)

    review = review_eodhd_campaign(tmp_path)
    by_criterion = {item.criterion: item for item in review.evidence}

    assert review.complete is True
    assert review.completed_case_count == 2
    assert (
        by_criterion[ProviderAcceptanceCriterion.REPRODUCIBLE_HISTORICAL_BACKFILL].status
        is ProviderEvidenceStatus.DEMONSTRATED
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.RAW_PRESERVATION].status
        is ProviderEvidenceStatus.DEMONSTRATED
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.CANONICAL_NORMALIZATION_QUALITY].status
        is ProviderEvidenceStatus.DEMONSTRATED
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.DELISTING_COVERAGE].status
        is ProviderEvidenceStatus.PARTIAL
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.CORPORATE_ACTION_HANDLING].status
        is ProviderEvidenceStatus.PARTIAL
    )


def test_partial_campaign_cannot_demonstrate_backfill_or_raw_preservation(tmp_path: Path) -> None:
    _build_campaign(tmp_path, complete=False)

    review = review_eodhd_campaign(tmp_path)
    by_criterion = {item.criterion: item for item in review.evidence}

    assert review.complete is False
    assert (
        by_criterion[ProviderAcceptanceCriterion.REPRODUCIBLE_HISTORICAL_BACKFILL].status
        is ProviderEvidenceStatus.PARTIAL
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.RAW_PRESERVATION].status
        is ProviderEvidenceStatus.PARTIAL
    )
    assert (
        by_criterion[ProviderAcceptanceCriterion.DELISTING_COVERAGE].status
        is ProviderEvidenceStatus.NOT_DEMONSTRATED
    )


def test_result_must_match_immutable_campaign_spec(tmp_path: Path) -> None:
    _build_campaign(tmp_path)
    result_path = (
        tmp_path
        / "campaign-state"
        / "eodhd-campaign-test"
        / "cases"
        / "active"
        / "result.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["symbol"] = "WRONG.US"
    _write(result_path, payload)

    with pytest.raises(EodhdCampaignReviewError, match="conflicts on symbol"):
        review_eodhd_campaign(tmp_path)


def test_ambiguous_summary_location_fails_closed(tmp_path: Path) -> None:
    _build_campaign(tmp_path)
    original = tmp_path / "report" / "eodhd-campaign-test" / "campaign-summary.json"
    duplicate = tmp_path / "report" / "another" / "campaign-summary.json"
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_bytes(original.read_bytes())

    with pytest.raises(EodhdCampaignReviewError, match="exactly one campaign summary"):
        review_eodhd_campaign(tmp_path)
