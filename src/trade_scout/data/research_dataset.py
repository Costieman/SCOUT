"""End-to-end loader from immutable canonical stores to the research contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, CanonicalDatasetManifest
from trade_scout.data.contracts import ResearchBar
from trade_scout.data.instrument_storage import InstrumentMasterManifest, InstrumentMasterStore
from trade_scout.data.serving import ResearchDataRequest, serve_research_bars
from trade_scout.universe.construction import (
    UniverseHistory,
    UniverseMeasurementPolicy,
    build_universe_history,
)
from trade_scout.universe.eligibility import UniverseRules


@dataclass(frozen=True, slots=True)
class ResearchDataset:
    """Research-ready rows plus the immutable identities that produced them."""

    rows: tuple[ResearchBar, ...]
    canonical_manifest: CanonicalDatasetManifest
    instrument_manifest: InstrumentMasterManifest
    universe_history: UniverseHistory


class ResearchDatasetLoader:
    """Load verified canonical state and materialize the provider-independent research boundary."""

    def __init__(self, root: Path) -> None:
        self._daily_bars = CanonicalDailyBarStore(root)
        self._instrument_master = InstrumentMasterStore(root)

    def load(
        self,
        *,
        instrument_snapshot_version: str,
        request: ResearchDataRequest,
        universe_rules: UniverseRules,
        measurement_policy: UniverseMeasurementPolicy,
    ) -> ResearchDataset:
        """Verify immutable stores, reconstruct historical eligibility, and serve research rows.

        The canonical and instrument stores perform checksum verification on load. Universe state is
        then reconstructed from canonical bars using only information available as of each session.
        No provider-native object crosses this boundary.
        """

        bars = self._daily_bars.load(request.dataset_version)
        canonical_manifest = self._daily_bars.get_manifest(request.dataset_version)
        assert canonical_manifest is not None
        instrument_snapshot = self._instrument_master.load(instrument_snapshot_version)

        universe_history = build_universe_history(
            bars,
            instrument_snapshot.instruments,
            rules=universe_rules,
            measurement_policy=measurement_policy,
            start=request.start,
            end=request.end,
        )
        rows = serve_research_bars(
            bars,
            eligibility_by_key=universe_history.eligibility_by_key,
            request=request,
        )
        return ResearchDataset(
            rows=rows,
            canonical_manifest=canonical_manifest,
            instrument_manifest=instrument_snapshot.manifest,
            universe_history=universe_history,
        )
