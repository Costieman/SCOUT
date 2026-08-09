"""Bounded EODHD campaign that exercises the full Phase 1 canonical promotion path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, CanonicalDatasetManifest
from trade_scout.data.contracts import CorporateActionType, DatasetVersion, PriceRepresentation
from trade_scout.data.instrument_master import instrument_from_primary_provider
from trade_scout.data.provider import CorporateActionRequest, DailyBarRequest, ProviderInstrument
from trade_scout.data.provider_adjustments import materialize_split_adjusted_bars
from trade_scout.data.provider_promotion import promote_provider_daily_bar_evaluation
from trade_scout.data.providers.eodhd import (
    EodhdAdapter,
    EodhdHttpClient,
    EodhdInstrumentLink,
    EodhdRawResponseCapture,
)
from trade_scout.data.providers.eodhd_adjustments import normalize_eodhd_adjustment_actions
from trade_scout.data.providers.eodhd_resilience import (
    EodhdClassifyingUrllibTransport,
    EodhdRetryPolicy,
    EodhdRetryingBytesTransport,
)
from trade_scout.data.raw_store import Primitive, RawBatchStore


class EodhdCampaignError(ValueError):
    """Raised when a bounded EODHD evaluation case cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class EodhdCampaignCase:
    """One explicit active or delisted EODHD security/date-range evaluation case."""

    symbol: str
    start: date
    end: date
    expected_active: bool

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("EODHD campaign symbol must be non-empty")
        if self.end < self.start:
            raise ValueError("EODHD campaign end must be on or after start")


@dataclass(frozen=True, slots=True)
class EodhdCanonicalCaseEvidence:
    """Evidence produced after raw capture, adjustment materialization, and canonical promotion."""

    symbol: str
    provider_instrument_id: str
    expected_active: bool
    bar_count: int
    action_count: int
    split_count: int
    dividend_count: int
    raw_batch_ids: tuple[str, ...]
    manifest: CanonicalDatasetManifest


class EodhdTrackingRawCapture(EodhdRawResponseCapture):
    """Persist exact EODHD bytes and expose the immutable batch IDs for provenance."""

    def __init__(self, store: RawBatchStore) -> None:
        self._store = store
        self._batch_ids: list[str] = []

    @property
    def batch_ids(self) -> tuple[str, ...]:
        """Return captured batch identities in request order."""

        return tuple(self._batch_ids)

    def capture(
        self,
        payload: bytes,
        *,
        endpoint: str,
        request_parameters: Mapping[str, Primitive],
    ) -> None:
        """Persist one exact response and remember its generated immutable batch identity."""

        batch_id = f"eodhd-campaign-{len(self._batch_ids) + 1:04d}-{uuid4().hex}"
        record = self._store.persist(
            payload,
            batch_id=batch_id,
            provider_id="eodhd",
            endpoint=endpoint,
            retrieval_time=datetime.now(UTC),
            request_parameters=request_parameters,
            media_type="application/json",
        )
        self._batch_ids.append(record.manifest.batch_id)


def run_eodhd_canonical_case(
    api_token: str,
    case: EodhdCampaignCase,
    *,
    raw_root: Path,
    canonical_store: CanonicalDailyBarStore,
    dataset_id: str,
    dataset_version: DatasetVersion,
    created_at: datetime,
    transformation_version: str,
    adjustment_policy_version: str,
    universe_construction_version: str,
    quality_check_version: str,
    retry_policy: EodhdRetryPolicy = EodhdRetryPolicy(),
) -> EodhdCanonicalCaseEvidence:
    """Exercise EODHD raw -> identity -> actions -> normalization -> canonical promotion.

    The case deliberately requires an ISIN-backed EODHD identity. Current/delisted inventories are
    used only to identify the requested evaluation security; they are never projected backward as
    a historical universe. Corporate-action absence is treated as zero only after both split and
    dividend endpoints have been queried for the exact bar interval. Classified transient and
    throttling failures use bounded retry; authentication and permanent request errors fail early.
    """

    capture = EodhdTrackingRawCapture(RawBatchStore(raw_root))
    transport = EodhdRetryingBytesTransport(
        EodhdClassifyingUrllibTransport(),
        policy=retry_policy,
    )
    client = EodhdHttpClient(api_token, transport=transport, raw_capture=capture)
    inventory_adapter = EodhdAdapter(client)
    instrument = _select_instrument(
        tuple(inventory_adapter.get_instruments()),
        symbol=case.symbol,
        expected_active=case.expected_active,
    )
    if instrument.source_fields.get("identity_quality") != "ISIN":
        raise EodhdCampaignError(
            f"EODHD campaign requires durable ISIN identity for {instrument.symbol}"
        )

    adapter = EodhdAdapter(
        client,
        instrument_links=(
            EodhdInstrumentLink(
                query_symbol=instrument.symbol,
                provider_instrument_id=instrument.provider_instrument_id,
            ),
        ),
    )
    bars = tuple(
        adapter.get_daily_bars(
            DailyBarRequest(
                start=case.start,
                end=case.end,
                provider_symbols=(instrument.symbol,),
                adjustment=PriceRepresentation.RAW,
                run_id=f"eodhd-canonical-evaluation:{dataset_version}:{instrument.symbol}",
            )
        )
    )
    actions = normalize_eodhd_adjustment_actions(
        adapter.get_corporate_actions(
            CorporateActionRequest(
                start=case.start,
                end=case.end,
                provider_symbols=(instrument.symbol,),
            )
        )
    )
    adjusted_bars = materialize_split_adjusted_bars(
        bars,
        actions,
        corporate_action_coverage_complete=True,
    )
    canonical_instrument = instrument_from_primary_provider(instrument)
    promotion = promote_provider_daily_bar_evaluation(
        adjusted_bars,
        instruments=(canonical_instrument,),
        store=canonical_store,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        primary_provider_id="eodhd",
        source_batch_ids=capture.batch_ids,
        created_at=created_at,
        transformation_version=transformation_version,
        adjustment_policy_version=adjustment_policy_version,
        universe_construction_version=universe_construction_version,
        quality_check_version=quality_check_version,
    )
    return EodhdCanonicalCaseEvidence(
        symbol=instrument.symbol,
        provider_instrument_id=instrument.provider_instrument_id,
        expected_active=case.expected_active,
        bar_count=len(adjusted_bars),
        action_count=len(actions),
        split_count=sum(action.action_type is CorporateActionType.SPLIT for action in actions),
        dividend_count=sum(
            action.action_type is CorporateActionType.CASH_DIVIDEND for action in actions
        ),
        raw_batch_ids=capture.batch_ids,
        manifest=promotion.manifest,
    )


def _select_instrument(
    instruments: tuple[ProviderInstrument, ...],
    *,
    symbol: str,
    expected_active: bool,
) -> ProviderInstrument:
    normalized = symbol.strip().upper()
    matches = tuple(
        instrument
        for instrument in instruments
        if instrument.symbol.upper() == normalized and instrument.active is expected_active
    )
    if len(matches) != 1:
        raise EodhdCampaignError(
            f"expected exactly one EODHD {normalized} instrument with active={expected_active}; "
            f"found {len(matches)}"
        )
    return matches[0]
