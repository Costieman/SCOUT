"""Aggregate a completed representative EODHD campaign into one canonical dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    SecurityType,
)


class EodhdCampaignAggregateError(ValueError):
    """Raised when completed campaign evidence cannot be aggregated safely."""


@dataclass(frozen=True, slots=True)
class EodhdCampaignAggregate:
    """One immutable canonical dataset assembled from all completed campaign cases."""

    campaign_id: str
    case_count: int
    instruments: tuple[InstrumentRecord, ...]
    manifest: CanonicalDatasetManifest


def aggregate_eodhd_campaign(
    *,
    campaign_root: Path,
    case_runtime_root: Path,
    target_store: CanonicalDailyBarStore,
    dataset_id: str,
    dataset_version: DatasetVersion,
    created_at: datetime,
) -> EodhdCampaignAggregate:
    """Verify a complete campaign, re-version its case bars, and promote one combined dataset."""

    campaign = _read_json(campaign_root / "campaign.json")
    checkpoint = _read_json(campaign_root / "checkpoint.json")
    campaign_id = _required_text(campaign.get("campaign_id"), field="campaign_id")
    if checkpoint.get("campaign_id") != campaign_id:
        raise EodhdCampaignAggregateError("campaign/checkpoint identities do not match")

    raw_cases = campaign.get("cases")
    completed_ids = checkpoint.get("completed_case_ids")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EodhdCampaignAggregateError("campaign cases must be a non-empty list")
    if not isinstance(completed_ids, list) or not all(
        isinstance(item, str) for item in completed_ids
    ):
        raise EodhdCampaignAggregateError("checkpoint completed_case_ids are invalid")

    case_ids: list[str] = []
    for case in raw_cases:
        if not isinstance(case, dict):
            raise EodhdCampaignAggregateError("campaign contains a malformed case")
        case_ids.append(_required_text(case.get("case_id"), field="case_id"))
    if tuple(completed_ids) != tuple(case_ids):
        raise EodhdCampaignAggregateError("campaign must be fully completed before aggregation")

    bars: list[DailyBar] = []
    instruments: list[InstrumentRecord] = []
    source_batch_ids: list[str] = []
    seen_instruments: set[InstrumentId] = set()

    for case_id in case_ids:
        result = _read_json(campaign_root / "cases" / case_id / "result.json")
        if result.get("case_id") != case_id:
            raise EodhdCampaignAggregateError(f"case result identity mismatch for {case_id}")
        case_dataset_version = DatasetVersion(
            _required_text(result.get("dataset_version"), field="dataset_version")
        )
        case_store = CanonicalDailyBarStore(case_runtime_root / case_id / "data")
        case_bars = case_store.load(case_dataset_version)
        expected_count = result.get("canonical_record_count")
        if isinstance(expected_count, bool) or not isinstance(expected_count, int):
            raise EodhdCampaignAggregateError(
                f"case {case_id} canonical_record_count is invalid"
            )
        if len(case_bars) != expected_count:
            raise EodhdCampaignAggregateError(f"case {case_id} canonical record count changed")

        bars.extend(replace(bar, dataset_version=dataset_version) for bar in case_bars)

        instrument = _instrument_from_result(result)
        if instrument.instrument_id in seen_instruments:
            raise EodhdCampaignAggregateError(
                f"campaign contains duplicate canonical instrument {instrument.instrument_id}"
            )
        seen_instruments.add(instrument.instrument_id)
        instruments.append(instrument)

        batch_ids = result.get("raw_batch_ids")
        if not isinstance(batch_ids, list) or not all(
            isinstance(item, str) and item for item in batch_ids
        ):
            raise EodhdCampaignAggregateError(f"case {case_id} raw_batch_ids are invalid")
        source_batch_ids.extend(batch_ids)

    if len(source_batch_ids) != len(set(source_batch_ids)):
        raise EodhdCampaignAggregateError("campaign raw provenance contains duplicate batch IDs")

    manifest = target_store.promote(
        bars,
        DatasetPromotionRequest(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            primary_provider_id="eodhd",
            created_at=created_at,
            source_batch_ids=tuple(source_batch_ids),
            transformation_version="provider-normalization-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="representative-eodhd-campaign-v1",
            quality_check_version="daily-bar-quality-v1",
        ),
    )
    return EodhdCampaignAggregate(
        campaign_id=campaign_id,
        case_count=len(case_ids),
        instruments=tuple(instruments),
        manifest=manifest,
    )


def _instrument_from_result(payload: dict[str, object]) -> InstrumentRecord:
    security_type_raw = _required_text(payload.get("security_type"), field="security_type")
    try:
        security_type = SecurityType(security_type_raw)
    except ValueError as exc:
        raise EodhdCampaignAggregateError(f"unsupported security_type {security_type_raw}") from exc
    first_trade_date = _optional_date(payload.get("first_trade_date"), field="first_trade_date")
    delisting_date = _optional_date(payload.get("delisting_date"), field="delisting_date")
    provider_instrument_id = _required_text(
        payload.get("provider_instrument_id"), field="provider_instrument_id"
    )
    instrument_id = _required_text(payload.get("instrument_id"), field="instrument_id")
    return InstrumentRecord(
        instrument_id=InstrumentId(instrument_id),
        primary_symbol=_required_text(payload.get("symbol"), field="symbol"),
        name=_required_text(payload.get("name"), field="name"),
        exchange=_required_text(payload.get("exchange"), field="exchange"),
        security_type=security_type,
        currency=_required_text(payload.get("currency"), field="currency"),
        first_trade_date=first_trade_date,
        delisting_date=delisting_date,
        provider_ids={"eodhd": provider_instrument_id},
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EodhdCampaignAggregateError(f"cannot read campaign evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EodhdCampaignAggregateError(f"campaign evidence is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EodhdCampaignAggregateError(f"campaign evidence root must be an object: {path}")
    return payload


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EodhdCampaignAggregateError(f"{field} must be non-empty text")
    return value.strip()


def _optional_date(value: object, *, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EodhdCampaignAggregateError(f"{field} must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EodhdCampaignAggregateError(f"{field} must be an ISO date or null") from exc
