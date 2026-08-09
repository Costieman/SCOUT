from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.providers.eodhd_campaign_aggregate import (
    EodhdCampaignAggregateError,
    aggregate_eodhd_campaign,
)


def _bar(instrument_id: str, trade_date: date, dataset_version: DatasetVersion) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=10.0,
        high_raw=11.0,
        low_raw=9.0,
        close_raw=10.5,
        volume_raw=1000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=10.0,
        high_split_adjusted=11.0,
        low_split_adjusted=9.0,
        close_split_adjusted=10.5,
        provider_id="eodhd",
        dataset_version=dataset_version,
        quality_status=QualityStatus.PASS,
    )


def _write_case(
    root: Path,
    *,
    case_id: str,
    instrument_id: str,
    symbol: str,
    dataset_version: str,
    batch_id: str,
    delisting_date: str | None,
) -> None:
    version = DatasetVersion(dataset_version)
    store = CanonicalDailyBarStore(root / "case-runtime" / case_id / "data")
    manifest = store.promote(
        (_bar(instrument_id, date(2020, 1, 2), version),),
        DatasetPromotionRequest(
            dataset_id=f"case:{case_id}",
            dataset_version=version,
            primary_provider_id="eodhd",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_batch_ids=(batch_id,),
            transformation_version="provider-normalization-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="bounded-provider-evidence-v1",
            quality_check_version="daily-bar-quality-v1",
        ),
    )
    result = {
        "case_id": case_id,
        "symbol": symbol,
        "provider_instrument_id": f"eodhd:isin:{instrument_id}",
        "instrument_id": instrument_id,
        "name": f"{symbol} Corp",
        "exchange": "NYSE" if symbol == "AAA" else "NASDAQ",
        "security_type": "common_stock",
        "currency": "USD",
        "first_trade_date": "2010-01-04",
        "delisting_date": delisting_date,
        "raw_batch_ids": [batch_id],
        "dataset_version": dataset_version,
        "canonical_record_count": manifest.record_count,
    }
    result_path = root / "campaign-state" / "campaign-1" / "cases" / case_id / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result), encoding="utf-8")


def _write_campaign(root: Path, completed: list[str]) -> None:
    campaign_root = root / "campaign-state" / "campaign-1"
    campaign_root.mkdir(parents=True, exist_ok=True)
    campaign_root.joinpath("campaign.json").write_text(
        json.dumps(
            {
                "campaign_id": "campaign-1",
                "cases": [{"case_id": "active"}, {"case_id": "delisted"}],
            }
        ),
        encoding="utf-8",
    )
    campaign_root.joinpath("checkpoint.json").write_text(
        json.dumps({"campaign_id": "campaign-1", "completed_case_ids": completed}),
        encoding="utf-8",
    )


def test_aggregate_combines_complete_campaign_into_one_canonical_dataset(tmp_path: Path) -> None:
    _write_campaign(tmp_path, ["active", "delisted"])
    _write_case(
        tmp_path,
        case_id="active",
        instrument_id="instrument-a",
        symbol="AAA",
        dataset_version="case-active-v1",
        batch_id="batch-active",
        delisting_date=None,
    )
    _write_case(
        tmp_path,
        case_id="delisted",
        instrument_id="instrument-b",
        symbol="BBB",
        dataset_version="case-delisted-v1",
        batch_id="batch-delisted",
        delisting_date="2021-02-01",
    )

    target_store = CanonicalDailyBarStore(tmp_path / "aggregate")
    aggregate = aggregate_eodhd_campaign(
        campaign_root=tmp_path / "campaign-state" / "campaign-1",
        case_runtime_root=tmp_path / "case-runtime",
        target_store=target_store,
        dataset_id="representative",
        dataset_version=DatasetVersion("representative-v1"),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert aggregate.campaign_id == "campaign-1"
    assert aggregate.case_count == 2
    assert aggregate.manifest.record_count == 2
    assert aggregate.manifest.source_batch_ids == ("batch-active", "batch-delisted")
    assert {str(item.instrument_id) for item in aggregate.instruments} == {
        "instrument-a",
        "instrument-b",
    }
    loaded = target_store.load(DatasetVersion("representative-v1"))
    assert len(loaded) == 2
    assert {str(bar.dataset_version) for bar in loaded} == {"representative-v1"}


def test_aggregate_fails_closed_until_every_campaign_case_is_complete(tmp_path: Path) -> None:
    _write_campaign(tmp_path, ["active"])

    with pytest.raises(EodhdCampaignAggregateError, match="fully completed"):
        aggregate_eodhd_campaign(
            campaign_root=tmp_path / "campaign-state" / "campaign-1",
            case_runtime_root=tmp_path / "case-runtime",
            target_store=CanonicalDailyBarStore(tmp_path / "aggregate"),
            dataset_id="representative",
            dataset_version=DatasetVersion("representative-v1"),
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
