"""Construct reviewed instrument/symbol-history candidates without ticker-derived identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid5

from trade_scout.data.contracts import (
    InstrumentId,
    InstrumentRecord,
    SecurityType,
    SymbolHistoryRecord,
)

_REVIEWED_IDENTITY_NAMESPACE = UUID("f7d517c0-53c1-52b7-a9bd-5a9ab5d17fea")


class ReviewedIdentitySnapshotError(RuntimeError):
    """Raised when reviewed identity evidence is incomplete or contradictory."""


@dataclass(frozen=True, slots=True)
class ReviewedSymbolInterval:
    """One explicitly evidenced dated symbol assignment from a review seed."""

    symbol: str
    exchange: str
    effective_from: date
    effective_to: date | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewedIdentitySeed:
    """Human-reviewed seed for one permanent internal identity candidate."""

    review_id: str
    primary_symbol: str
    name: str
    exchange: str
    security_type: SecurityType
    currency: str
    first_trade_date: date | None
    delisting_date: date | None
    provider_links: Mapping[str, str]
    provider_query_symbols: Mapping[str, str]
    symbol_history: tuple[ReviewedSymbolInterval, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewedIdentitySeedSet:
    """Versioned reviewed identity inputs independent of any private workspace."""

    snapshot_version: str
    primary_provider_id: str
    identity_definition_version: str
    symbol_history_definition_version: str
    seeds: tuple[ReviewedIdentitySeed, ...]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ProviderSeriesLink:
    """Explicit query-symbol to stable reviewed provider-series identity mapping."""

    instrument_id: InstrumentId
    review_id: str
    provider_id: str
    provider_series_id: str
    query_symbol: str


@dataclass(frozen=True, slots=True)
class IdentityCoverageGap:
    """Observed provider-history interval lacking reviewed canonical symbol coverage."""

    instrument_id: InstrumentId
    review_id: str
    provider_id: str
    query_symbol: str
    gap_start: date
    gap_end: date
    reason: str
    known_predecessor_symbol: str | None


@dataclass(frozen=True, slots=True)
class ReviewedIdentitySnapshotCandidate:
    """Metadata-only identity candidate; not a promoted canonical snapshot."""

    schema_version: str
    snapshot_version: str
    primary_provider_id: str
    identity_definition_version: str
    symbol_history_definition_version: str
    identity_seed_sha256: str
    lineage_audit_sha256: str
    instruments: tuple[InstrumentRecord, ...]
    symbol_history: tuple[SymbolHistoryRecord, ...]
    provider_series_links: tuple[ProviderSeriesLink, ...]
    coverage_gaps: tuple[IdentityCoverageGap, ...]
    evidence_refs: tuple[str, ...]

    @property
    def promotion_ready(self) -> bool:
        """Require reviewed symbol coverage for every audited observed-history span."""

        return not self.coverage_gaps

    @property
    def fully_covered_instrument_count(self) -> int:
        """Count candidate instruments without any unresolved audited-history span."""

        blocked = {gap.instrument_id for gap in self.coverage_gaps}
        return sum(item.instrument_id not in blocked for item in self.instruments)


def derive_reviewed_instrument_id(review_id: str) -> InstrumentId:
    """Derive an opaque stable ID from review identity, never from ticker."""

    normalized = review_id.strip()
    if not normalized:
        raise ValueError("review_id must be non-empty")
    value = uuid5(_REVIEWED_IDENTITY_NAMESPACE, normalized)
    return InstrumentId(f"tsi_{value.hex}")


def load_reviewed_identity_seed_set(path: Path) -> ReviewedIdentitySeedSet:
    """Load and strictly validate reviewed permanent-identity inputs."""

    raw_bytes = _read_bytes(path, "reviewed identity seed config")
    payload = _json_object(raw_bytes, "reviewed identity seed config")
    if payload.get("schema_version") != "reviewed-identity-seeds-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported reviewed identity seed schema")

    primary_provider_id = _required_text(
        payload.get("primary_provider_id"),
        "primary_provider_id",
    )
    raw_seeds = _object_list(payload.get("seeds"), "seeds")
    if not raw_seeds:
        raise ReviewedIdentitySnapshotError("reviewed identity seeds must not be empty")
    seeds = tuple(_parse_seed(item, primary_provider_id) for item in raw_seeds)
    _validate_seed_set(seeds)

    return ReviewedIdentitySeedSet(
        snapshot_version=_required_text(
            payload.get("snapshot_version"),
            "snapshot_version",
        ),
        primary_provider_id=primary_provider_id,
        identity_definition_version=_required_text(
            payload.get("identity_definition_version"),
            "identity_definition_version",
        ),
        symbol_history_definition_version=_required_text(
            payload.get("symbol_history_definition_version"),
            "symbol_history_definition_version",
        ),
        seeds=tuple(sorted(seeds, key=lambda item: item.review_id)),
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def build_reviewed_identity_snapshot_candidate(
    *,
    seed_set: ReviewedIdentitySeedSet,
    lineage_audit_path: Path,
) -> ReviewedIdentitySnapshotCandidate:
    """Build a candidate while leaving unsupported predecessor spans unresolved."""

    audit_bytes = _read_bytes(lineage_audit_path, "Tiingo lineage audit")
    audit = _json_object(audit_bytes, "Tiingo lineage audit")
    if audit.get("schema_version") != "tiingo-lineage-audit-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported Tiingo lineage audit schema")
    observations = _index_audit_observations(
        _object_list(audit.get("observations"), "observations")
    )

    instruments: list[InstrumentRecord] = []
    history: list[SymbolHistoryRecord] = []
    links: list[ProviderSeriesLink] = []
    gaps: list[IdentityCoverageGap] = []
    evidence_refs: set[str] = set()

    for seed in seed_set.seeds:
        instrument_id = derive_reviewed_instrument_id(seed.review_id)
        instruments.append(_instrument_from_seed(seed, instrument_id))
        evidence_refs.update(seed.evidence_refs)

        for interval in seed.symbol_history:
            history.append(
                SymbolHistoryRecord(
                    instrument_id=instrument_id,
                    symbol=interval.symbol,
                    exchange=interval.exchange,
                    effective_from=interval.effective_from,
                    effective_to=interval.effective_to,
                )
            )
            evidence_refs.update(interval.evidence_refs)

        query_symbol = seed.provider_query_symbols["tiingo"]
        provider_series_id = seed.provider_links["tiingo"]
        links.append(
            ProviderSeriesLink(
                instrument_id=instrument_id,
                review_id=seed.review_id,
                provider_id="tiingo",
                provider_series_id=provider_series_id,
                query_symbol=query_symbol,
            )
        )

        observation = observations.get(query_symbol)
        if observation is None:
            raise ReviewedIdentitySnapshotError(
                f"review seed {seed.review_id} has no matching Tiingo lineage audit observation"
            )
        observed_first = _required_date(
            observation.get("observed_first_date"),
            f"{query_symbol}.observed_first_date",
        )
        gaps.extend(
            _coverage_gaps_for_seed(
                seed=seed,
                instrument_id=instrument_id,
                observed_first=observed_first,
                predecessor=_known_predecessor_symbol(observation),
            )
        )
        evidence_refs.update(_audit_evidence_refs(observation))

    canonical_history = tuple(
        sorted(
            history,
            key=lambda item: (
                str(item.instrument_id),
                item.effective_from,
                item.effective_to or date.max,
                item.symbol,
            ),
        )
    )
    _validate_candidate_history(canonical_history)

    return ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version=seed_set.snapshot_version,
        primary_provider_id=seed_set.primary_provider_id,
        identity_definition_version=seed_set.identity_definition_version,
        symbol_history_definition_version=seed_set.symbol_history_definition_version,
        identity_seed_sha256=seed_set.source_sha256,
        lineage_audit_sha256=hashlib.sha256(audit_bytes).hexdigest(),
        instruments=tuple(sorted(instruments, key=lambda item: str(item.instrument_id))),
        symbol_history=canonical_history,
        provider_series_links=tuple(
            sorted(links, key=lambda item: (item.provider_id, item.query_symbol))
        ),
        coverage_gaps=tuple(
            sorted(
                gaps,
                key=lambda item: (
                    str(item.instrument_id),
                    item.gap_start,
                    item.gap_end,
                ),
            )
        ),
        evidence_refs=tuple(sorted(evidence_refs)),
    )


def persist_reviewed_identity_snapshot_candidate(
    path: Path,
    candidate: ReviewedIdentitySnapshotCandidate,
) -> None:
    """Persist a metadata-only candidate atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_candidate_payload(candidate), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_reviewed_identity_snapshot_candidate(
    path: Path,
) -> ReviewedIdentitySnapshotCandidate:
    """Reload a persisted candidate and revalidate identity/history structure."""

    payload = _json_object(_read_bytes(path, "reviewed identity candidate"), "candidate")
    if payload.get("schema_version") != "reviewed-identity-candidate-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported reviewed identity candidate schema")

    instruments = tuple(
        _instrument_from_payload(item)
        for item in _object_list(payload.get("instruments"), "instruments")
    )
    history = tuple(
        _history_from_payload(item)
        for item in _object_list(payload.get("symbol_history"), "symbol_history")
    )
    links = tuple(
        _link_from_payload(item)
        for item in _object_list(
            payload.get("provider_series_links"),
            "provider_series_links",
        )
    )
    gaps = tuple(
        _gap_from_payload(item)
        for item in _object_list(payload.get("coverage_gaps"), "coverage_gaps")
    )
    primary_provider_id = _required_text(
        payload.get("primary_provider_id"),
        "primary_provider_id",
    )
    _validate_loaded_candidate(
        instruments,
        history,
        links,
        gaps,
        primary_provider_id=primary_provider_id,
    )

    return ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version=_required_text(
            payload.get("snapshot_version"),
            "snapshot_version",
        ),
        primary_provider_id=primary_provider_id,
        identity_definition_version=_required_text(
            payload.get("identity_definition_version"),
            "identity_definition_version",
        ),
        symbol_history_definition_version=_required_text(
            payload.get("symbol_history_definition_version"),
            "symbol_history_definition_version",
        ),
        identity_seed_sha256=_sha256_text(
            payload.get("identity_seed_sha256"),
            "identity_seed_sha256",
        ),
        lineage_audit_sha256=_sha256_text(
            payload.get("lineage_audit_sha256"),
            "lineage_audit_sha256",
        ),
        instruments=instruments,
        symbol_history=history,
        provider_series_links=links,
        coverage_gaps=gaps,
        evidence_refs=_text_tuple(
            payload.get("evidence_refs"),
            "evidence_refs",
            allow_empty=True,
        ),
    )


def provider_series_link_for_query(
    candidate: ReviewedIdentitySnapshotCandidate,
    *,
    provider_id: str,
    query_symbol: str,
) -> ProviderSeriesLink | None:
    """Resolve one explicitly reviewed provider query to its stable series identity."""

    matches = tuple(
        item
        for item in candidate.provider_series_links
        if item.provider_id == provider_id and item.query_symbol == query_symbol
    )
    if len(matches) > 1:
        raise ReviewedIdentitySnapshotError(
            f"provider query {provider_id}:{query_symbol} maps to multiple reviewed series"
        )
    return matches[0] if matches else None


def _parse_seed(raw: Mapping[str, object], primary_provider_id: str) -> ReviewedIdentitySeed:
    review_id = _required_text(raw.get("review_id"), "review_id")
    provider_links = _text_mapping(raw.get("provider_links"), "provider_links")
    provider_queries = _text_mapping(
        raw.get("provider_query_symbols"),
        "provider_query_symbols",
    )
    if provider_links.get(primary_provider_id) != review_id:
        raise ReviewedIdentitySnapshotError(
            f"seed {review_id} must use its review_id as the primary reviewed identity"
        )
    if "tiingo" not in provider_links or "tiingo" not in provider_queries:
        raise ReviewedIdentitySnapshotError(
            f"seed {review_id} must include explicit Tiingo series and query linkage"
        )
    if provider_links["tiingo"] == provider_queries["tiingo"]:
        raise ReviewedIdentitySnapshotError(
            f"seed {review_id} cannot use current ticker as stable Tiingo series ID"
        )

    intervals = tuple(
        _parse_interval(item, review_id)
        for item in _object_list(raw.get("symbol_history"), "symbol_history")
    )
    if not intervals:
        raise ReviewedIdentitySnapshotError(f"seed {review_id} requires symbol history")
    _validate_seed_intervals(review_id, intervals)

    primary_symbol = _required_text(raw.get("primary_symbol"), "primary_symbol")
    open_intervals = tuple(item for item in intervals if item.effective_to is None)
    if len(open_intervals) != 1 or open_intervals[0].symbol != primary_symbol:
        raise ReviewedIdentitySnapshotError(
            f"seed {review_id} must have exactly one open current-symbol interval"
        )

    try:
        security_type = SecurityType(_required_text(raw.get("security_type"), "security_type"))
    except ValueError as exc:
        raise ReviewedIdentitySnapshotError(f"seed {review_id} has invalid security_type") from exc

    first_trade = _optional_date(raw.get("first_trade_date"), "first_trade_date")
    delisting = _optional_date(raw.get("delisting_date"), "delisting_date")
    if first_trade is not None and delisting is not None and delisting < first_trade:
        raise ReviewedIdentitySnapshotError(f"seed {review_id} delists before first trade")

    return ReviewedIdentitySeed(
        review_id=review_id,
        primary_symbol=primary_symbol,
        name=_required_text(raw.get("name"), "name"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        security_type=security_type,
        currency=_required_text(raw.get("currency"), "currency"),
        first_trade_date=first_trade,
        delisting_date=delisting,
        provider_links=MappingProxyType(provider_links),
        provider_query_symbols=MappingProxyType(provider_queries),
        symbol_history=tuple(sorted(intervals, key=lambda item: item.effective_from)),
        evidence_refs=_text_tuple(raw.get("evidence_refs"), "evidence_refs"),
    )


def _parse_interval(
    raw: Mapping[str, object],
    review_id: str,
) -> ReviewedSymbolInterval:
    start = _required_date(raw.get("effective_from"), "effective_from")
    end = _optional_date(raw.get("effective_to"), "effective_to")
    if end is not None and end < start:
        raise ReviewedIdentitySnapshotError(
            f"symbol-history interval for {review_id} ends before it starts"
        )
    return ReviewedSymbolInterval(
        symbol=_required_text(raw.get("symbol"), "symbol"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        effective_from=start,
        effective_to=end,
        evidence_refs=_text_tuple(raw.get("evidence_refs"), "evidence_refs"),
    )


def _instrument_from_seed(
    seed: ReviewedIdentitySeed,
    instrument_id: InstrumentId,
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=instrument_id,
        primary_symbol=seed.primary_symbol,
        name=seed.name,
        exchange=seed.exchange,
        security_type=seed.security_type,
        currency=seed.currency,
        first_trade_date=seed.first_trade_date,
        delisting_date=seed.delisting_date,
        provider_ids=MappingProxyType(dict(seed.provider_links)),
    )


def _validate_seed_set(seeds: tuple[ReviewedIdentitySeed, ...]) -> None:
    review_ids: set[str] = set()
    provider_owners: dict[tuple[str, str], str] = {}
    query_owners: dict[tuple[str, str], str] = {}
    for seed in seeds:
        if seed.review_id in review_ids:
            raise ReviewedIdentitySnapshotError(f"duplicate review_id {seed.review_id}")
        review_ids.add(seed.review_id)
        for provider_id, series_id in seed.provider_links.items():
            key = (provider_id, series_id)
            prior = provider_owners.get(key)
            if prior is not None and prior != seed.review_id:
                raise ReviewedIdentitySnapshotError(
                    f"provider series {provider_id}:{series_id} has multiple owners"
                )
            provider_owners[key] = seed.review_id
        for provider_id, query_symbol in seed.provider_query_symbols.items():
            key = (provider_id, query_symbol)
            prior = query_owners.get(key)
            if prior is not None and prior != seed.review_id:
                raise ReviewedIdentitySnapshotError(
                    f"provider query {provider_id}:{query_symbol} has multiple owners"
                )
            query_owners[key] = seed.review_id


def _validate_seed_intervals(
    review_id: str,
    intervals: tuple[ReviewedSymbolInterval, ...],
) -> None:
    ordered = sorted(intervals, key=lambda item: item.effective_from)
    for previous, current in pairwise(ordered):
        if previous.effective_to is None or current.effective_from <= previous.effective_to:
            raise ReviewedIdentitySnapshotError(
                f"seed {review_id} has overlapping symbol-history intervals"
            )


def _coverage_gaps_for_seed(
    *,
    seed: ReviewedIdentitySeed,
    instrument_id: InstrumentId,
    observed_first: date,
    predecessor: str | None,
) -> tuple[IdentityCoverageGap, ...]:
    intervals = tuple(sorted(seed.symbol_history, key=lambda item: item.effective_from))
    query_symbol = seed.provider_query_symbols["tiingo"]
    gaps: list[IdentityCoverageGap] = []

    earliest = intervals[0].effective_from
    if observed_first < earliest:
        gaps.append(
            IdentityCoverageGap(
                instrument_id=instrument_id,
                review_id=seed.review_id,
                provider_id="tiingo",
                query_symbol=query_symbol,
                gap_start=observed_first,
                gap_end=earliest - timedelta(days=1),
                reason="PREHISTORY_SYMBOL_START_UNRESOLVED",
                known_predecessor_symbol=predecessor,
            )
        )

    for previous, current in pairwise(intervals):
        if previous.effective_to is None:
            break
        expected_next = previous.effective_to + timedelta(days=1)
        if current.effective_from <= expected_next:
            continue
        gaps.append(
            IdentityCoverageGap(
                instrument_id=instrument_id,
                review_id=seed.review_id,
                provider_id="tiingo",
                query_symbol=query_symbol,
                gap_start=expected_next,
                gap_end=current.effective_from - timedelta(days=1),
                reason="DATED_SYMBOL_HISTORY_GAP",
                known_predecessor_symbol=None,
            )
        )
    return tuple(gaps)


def _index_audit_observations(
    raw: tuple[Mapping[str, object], ...],
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for item in raw:
        symbol = _required_text(item.get("source_symbol"), "source_symbol")
        if symbol in result:
            raise ReviewedIdentitySnapshotError(f"duplicate lineage audit observation: {symbol}")
        result[symbol] = item
    return result


def _known_predecessor_symbol(observation: Mapping[str, object]) -> str | None:
    events = _object_list(observation.get("lineage_events"), "lineage_events")
    dated: list[tuple[date, str | None]] = []
    for event in events:
        effective = _required_date(event.get("effective_date"), "effective_date")
        raw_symbol = event.get("from_symbol")
        from_symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else None
        dated.append((effective, from_symbol or None))
    return None if not dated else sorted(dated, key=lambda item: item[0])[0][1]


def _audit_evidence_refs(observation: Mapping[str, object]) -> set[str]:
    refs: set[str] = set()
    for event in _object_list(observation.get("lineage_events"), "lineage_events"):
        source_url = event.get("source_url")
        if isinstance(source_url, str) and source_url.strip():
            refs.add(source_url.strip())
    return refs


def _validate_candidate_history(history: tuple[SymbolHistoryRecord, ...]) -> None:
    by_instrument: dict[InstrumentId, list[SymbolHistoryRecord]] = {}
    for record in history:
        by_instrument.setdefault(record.instrument_id, []).append(record)
    for instrument_id, records in by_instrument.items():
        ordered = sorted(records, key=lambda item: item.effective_from)
        for previous, current in pairwise(ordered):
            if previous.effective_to is None or current.effective_from <= previous.effective_to:
                raise ReviewedIdentitySnapshotError(
                    f"candidate has overlapping symbol history for {instrument_id}"
                )


def _candidate_payload(candidate: ReviewedIdentitySnapshotCandidate) -> dict[str, object]:
    return {
        "schema_version": candidate.schema_version,
        "snapshot_version": candidate.snapshot_version,
        "primary_provider_id": candidate.primary_provider_id,
        "identity_definition_version": candidate.identity_definition_version,
        "symbol_history_definition_version": candidate.symbol_history_definition_version,
        "identity_seed_sha256": candidate.identity_seed_sha256,
        "lineage_audit_sha256": candidate.lineage_audit_sha256,
        "promotion_ready": candidate.promotion_ready,
        "fully_covered_instrument_count": candidate.fully_covered_instrument_count,
        "instruments": [_instrument_payload(item) for item in candidate.instruments],
        "symbol_history": [_history_payload(item) for item in candidate.symbol_history],
        "provider_series_links": [_link_payload(item) for item in candidate.provider_series_links],
        "coverage_gaps": [_gap_payload(item) for item in candidate.coverage_gaps],
        "evidence_refs": list(candidate.evidence_refs),
    }


def _instrument_payload(item: InstrumentRecord) -> dict[str, object]:
    return {
        "instrument_id": str(item.instrument_id),
        "primary_symbol": item.primary_symbol,
        "name": item.name,
        "exchange": item.exchange,
        "security_type": item.security_type.value,
        "currency": item.currency,
        "first_trade_date": _date_text(item.first_trade_date),
        "delisting_date": _date_text(item.delisting_date),
        "provider_ids": dict(sorted(item.provider_ids.items())),
    }


def _history_payload(item: SymbolHistoryRecord) -> dict[str, object]:
    return {
        "instrument_id": str(item.instrument_id),
        "symbol": item.symbol,
        "exchange": item.exchange,
        "effective_from": item.effective_from.isoformat(),
        "effective_to": _date_text(item.effective_to),
    }


def _link_payload(item: ProviderSeriesLink) -> dict[str, object]:
    return {
        "instrument_id": str(item.instrument_id),
        "review_id": item.review_id,
        "provider_id": item.provider_id,
        "provider_series_id": item.provider_series_id,
        "query_symbol": item.query_symbol,
    }


def _gap_payload(item: IdentityCoverageGap) -> dict[str, object]:
    return {
        "instrument_id": str(item.instrument_id),
        "review_id": item.review_id,
        "provider_id": item.provider_id,
        "query_symbol": item.query_symbol,
        "gap_start": item.gap_start.isoformat(),
        "gap_end": item.gap_end.isoformat(),
        "reason": item.reason,
        "known_predecessor_symbol": item.known_predecessor_symbol,
    }


def _instrument_from_payload(raw: Mapping[str, object]) -> InstrumentRecord:
    try:
        security_type = SecurityType(_required_text(raw.get("security_type"), "security_type"))
    except ValueError as exc:
        raise ReviewedIdentitySnapshotError(
            "candidate instrument has invalid security_type"
        ) from exc
    return InstrumentRecord(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        primary_symbol=_required_text(raw.get("primary_symbol"), "primary_symbol"),
        name=_required_text(raw.get("name"), "name"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        security_type=security_type,
        currency=_required_text(raw.get("currency"), "currency"),
        first_trade_date=_optional_date(raw.get("first_trade_date"), "first_trade_date"),
        delisting_date=_optional_date(raw.get("delisting_date"), "delisting_date"),
        provider_ids=MappingProxyType(_text_mapping(raw.get("provider_ids"), "provider_ids")),
    )


def _history_from_payload(raw: Mapping[str, object]) -> SymbolHistoryRecord:
    return SymbolHistoryRecord(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        symbol=_required_text(raw.get("symbol"), "symbol"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        effective_from=_required_date(raw.get("effective_from"), "effective_from"),
        effective_to=_optional_date(raw.get("effective_to"), "effective_to"),
    )


def _link_from_payload(raw: Mapping[str, object]) -> ProviderSeriesLink:
    return ProviderSeriesLink(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        review_id=_required_text(raw.get("review_id"), "review_id"),
        provider_id=_required_text(raw.get("provider_id"), "provider_id"),
        provider_series_id=_required_text(
            raw.get("provider_series_id"),
            "provider_series_id",
        ),
        query_symbol=_required_text(raw.get("query_symbol"), "query_symbol"),
    )


def _gap_from_payload(raw: Mapping[str, object]) -> IdentityCoverageGap:
    raw_predecessor = raw.get("known_predecessor_symbol")
    if raw_predecessor is not None and not isinstance(raw_predecessor, str):
        raise ReviewedIdentitySnapshotError("known_predecessor_symbol must be text or null")
    return IdentityCoverageGap(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        review_id=_required_text(raw.get("review_id"), "review_id"),
        provider_id=_required_text(raw.get("provider_id"), "provider_id"),
        query_symbol=_required_text(raw.get("query_symbol"), "query_symbol"),
        gap_start=_required_date(raw.get("gap_start"), "gap_start"),
        gap_end=_required_date(raw.get("gap_end"), "gap_end"),
        reason=_required_text(raw.get("reason"), "reason"),
        known_predecessor_symbol=raw_predecessor,
    )


def _validate_loaded_candidate(
    instruments: tuple[InstrumentRecord, ...],
    history: tuple[SymbolHistoryRecord, ...],
    links: tuple[ProviderSeriesLink, ...],
    gaps: tuple[IdentityCoverageGap, ...],
    *,
    primary_provider_id: str,
) -> None:
    if not instruments:
        raise ReviewedIdentitySnapshotError("reviewed identity candidate must not be empty")
    by_id = {item.instrument_id: item for item in instruments}
    if len(by_id) != len(instruments):
        raise ReviewedIdentitySnapshotError("candidate contains duplicate instrument IDs")
    for instrument in instruments:
        if not instrument.provider_ids.get(primary_provider_id):
            raise ReviewedIdentitySnapshotError(
                f"candidate instrument {instrument.instrument_id} lacks primary review identity"
            )
    _validate_candidate_history(history)
    if any(item.instrument_id not in by_id for item in history):
        raise ReviewedIdentitySnapshotError(
            "symbol history references unknown candidate instrument"
        )
    for link in links:
        instrument = by_id.get(link.instrument_id)
        if instrument is None:
            raise ReviewedIdentitySnapshotError(
                "provider series link references unknown instrument"
            )
        if instrument.provider_ids.get(link.provider_id) != link.provider_series_id:
            raise ReviewedIdentitySnapshotError(
                "provider series link disagrees with candidate instrument provider identity"
            )
    if any(item.instrument_id not in by_id for item in gaps):
        raise ReviewedIdentitySnapshotError("coverage gap references unknown instrument")
    link_keys = {(item.provider_id, item.query_symbol) for item in links}
    if len(link_keys) != len(links):
        raise ReviewedIdentitySnapshotError("candidate contains duplicate provider query links")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ReviewedIdentitySnapshotError(f"cannot read {label}: {path}") from exc


def _json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewedIdentitySnapshotError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ReviewedIdentitySnapshotError(f"{label} root must be an object")
    return payload


def _object_list(value: object, field: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ReviewedIdentitySnapshotError(f"{field} must be an array")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ReviewedIdentitySnapshotError(f"{field} entries must be objects")
        result.append(item)
    return tuple(result)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedIdentitySnapshotError(f"{field} must be non-empty text")
    return value.strip()


def _text_mapping(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ReviewedIdentitySnapshotError(f"{field} must be a non-empty object")
    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _required_text(raw_key, field)
        result[key] = _required_text(raw_value, field)
    return result


def _text_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ReviewedIdentitySnapshotError(f"{field} must be an array of evidence references")
    result = tuple(_required_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ReviewedIdentitySnapshotError(f"{field} must not contain duplicates")
    return result


def _required_date(value: object, field: str) -> date:
    text = _required_text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ReviewedIdentitySnapshotError(f"{field} must be an ISO date") from exc


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    return _required_date(value, field)


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _sha256_text(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ReviewedIdentitySnapshotError(f"{field} must be a SHA-256 hex digest")
    return text
