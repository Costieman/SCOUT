"""Assess and benchmark one aggregated EODHD representative campaign dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion, InstrumentRecord
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
