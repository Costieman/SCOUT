"""Assess and benchmark one aggregated EODHD representative campaign dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    SecurityType,
)
from trade_scout.data.representative_sample import (
    RepresentativeSampleAssessment,
    RepresentativeSamplePolicy,
    assess_representative_sample,
)
from trade_scout.data.storage_benchmark import StorageBenchmarkResult, benchmark_registered_dataset


@dataclass(frozen=True, slots=True)
class EodhdCampaignBenchmarkEvidence:
    """Combined Phase 1 representativeness and storage evidence for one aggregate dataset."""

    dataset_version: DatasetVersion
    representative_sample: RepresentativeSampleAssessment
    storage_benchmark: StorageBenchmarkResult | None

    @property
    def representative_sample_accepted(self) -> bool:
        return self.representative_sample.accepted


def load_aggregate_campaign_instruments(path: Path) -> tuple[InstrumentRecord, ...]:
    """Load the instrument slice emitted by the aggregate campaign report."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("aggregate report must be a JSON object")
    raw_instruments = payload.get("instruments")
    if not isinstance(raw_instruments, list) or not raw_instruments:
        raise ValueError("aggregate report instruments must be a non-empty list")

    instruments: list[InstrumentRecord] = []
    for raw in raw_instruments:
        if not isinstance(raw, dict):
            raise ValueError("aggregate report instrument entries must be objects")
        instruments.append(
            InstrumentRecord(
                instrument_id=InstrumentId(_text(raw, "instrument_id")),
                primary_symbol=_text(raw, "symbol"),
                name=_text(raw, "name"),
                exchange=_text(raw, "exchange"),
                security_type=SecurityType(_text(raw, "security_type")),
                currency=_text(raw, "currency"),
                first_trade_date=_optional_date(raw.get("first_trade_date")),
                delisting_date=_optional_date(raw.get("delisting_date")),
                provider_ids={"eodhd": _text(raw, "provider_instrument_id")},
            )
        )
    return tuple(instruments)


def assess_and_benchmark_eodhd_campaign(
    *,
    source_root: Path,
    dataset_version: DatasetVersion,
    instruments: tuple[InstrumentRecord, ...],
    policy: RepresentativeSamplePolicy,
    benchmark_root: Path,
    query_start: date,
    query_end: date,
) -> EodhdCampaignBenchmarkEvidence:
    """Fail closed on sample scope before spending time benchmarking non-representative data."""

    store = CanonicalDailyBarStore(source_root)
    bars = store.load(dataset_version)
    assessment = assess_representative_sample(bars, instruments, policy=policy)
    if not assessment.accepted:
        return EodhdCampaignBenchmarkEvidence(
            dataset_version=dataset_version,
            representative_sample=assessment,
            storage_benchmark=None,
        )

    benchmark = benchmark_registered_dataset(
        source_root=source_root,
        dataset_version=dataset_version,
        benchmark_root=benchmark_root,
        query_start=query_start,
        query_end=query_end,
    )
    return EodhdCampaignBenchmarkEvidence(
        dataset_version=dataset_version,
        representative_sample=assessment,
        storage_benchmark=benchmark,
    )


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"aggregate report {key} must be non-empty text")
    return value.strip()


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("aggregate report dates must be ISO dates or null")
    return date.fromisoformat(value)
