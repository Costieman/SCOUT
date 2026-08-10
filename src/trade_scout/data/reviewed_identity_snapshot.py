"""Construct reviewed instrument/symbol-history candidates without ticker-derived identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
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
    """Human-reviewed seed used to construct a permanent internal identity candidate."""

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
    """Known interval where observed provider history lacks reviewed canonical symbol coverage."""

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
    """Metadata-only identity candidate; it is not a promoted canonical snapshot."""

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
        """Return true only when reviewed symbol history covers every audited observed-history span."""

        return not self.coverage_gaps

    @property
    def fully_covered_instrument_count(self) -> int:
        blocked = {gap.instrument_id for gap in self.coverage_gaps}
        return sum(item.instrument_id not in blocked for item in self.instruments)


def derive_reviewed_instrument_id(review_id: str) -> InstrumentId:
    """Derive an opaque stable ID from an explicit review identity, never from ticker."""

    normalized = review_id.strip()
    if not normalized:
        raise ValueError("review_id must be non-empty")
    value = uuid5(_REVIEWED_IDENTITY_NAMESPACE, normalized)
    return InstrumentId(f"tsi_{value.hex}")


def load_reviewed_identity_seed_set(path: Path) -> ReviewedIdentitySeedSet:
    """Load and strictly validate reviewed permanent-identity inputs."""

    raw_bytes = _read_bytes(path, "reviewed identity seed config")
    payload = _decode_object(raw_bytes, "reviewed identity seed config")
    if payload.get("schema_version") != "reviewed-identity-seeds-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported reviewed identity seed schema")

    snapshot_version = _required_text(payload.get("snapshot_version"), "snapshot_version")
    primary_provider_id = _required_text(
        payload.get("primary_provider_id"), "primary_provider_id"
    )
    identity_definition_version = _required_text(
        payload.get("identity_definition_version"), "identity_definition_version"
    )
    symbol_history_definition_version = _required_text(
        payload.get("symbol_history_definition_version"),
        "symbol_history_definition_version",
    )
    raw_seeds = payload.get("seeds")
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise ReviewedIdentitySnapshotError("reviewed identity seeds must be a non-empty array")

    seeds = tuple(_parse_seed(item, primary_provider_id) for item in raw_seeds)
    _validate_seed_set(seeds)
    return ReviewedIdentitySeedSet(
        snapshot_version=snapshot_version,
        primary_provider_id=primary_provider_id,
        identity_definition_version=identity_definition_version,
        symbol_history_definition_version=symbol_history_definition_version,
        seeds=tuple(sorted(seeds, key=lambda item: item.review_id)),
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def build_reviewed_identity_snapshot_candidate(
    *,
    seed_set: ReviewedIdentitySeedSet,
    lineage_audit_path: Path,
) -> ReviewedIdentitySnapshotCandidate:
    """Build a candidate while preserving unresolved historical-symbol spans as explicit gaps."""

    audit_bytes = _read_bytes(lineage_audit_path, "Tiingo lineage audit")
    audit = _decode_object(audit_bytes, "Tiingo lineage audit")
    if audit.get("schema_version") != "tiingo-lineage-audit-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported Tiingo lineage audit schema")
    raw_observations = audit.get("observations")
    if not isinstance(raw_observations, list):
        raise ReviewedIdentitySnapshotError("Tiingo lineage audit observations must be an array")
    observations = _index_audit_observations(raw_observations)

    instruments: list[InstrumentRecord] = []
    history: list[SymbolHistoryRecord] = []
    links: list[ProviderSeriesLink] = []
    gaps: list[IdentityCoverageGap] = []
    evidence: set[str] = set()

    for seed in seed_set.seeds:
        instrument_id = derive_reviewed_instrument_id(seed.review_id)
        instruments.append(
            InstrumentRecord(
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
        )
        evidence.update(seed.evidence_refs)
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
            evidence.update(interval.evidence_refs)

        tiingo_query = seed.provider_query_symbols.get("tiingo")
        tiingo_series = seed.provider_links.get("tiingo")
        if tiingo_query is None or tiingo_series is None:
            raise ReviewedIdentitySnapshotError(
                f"review seed {seed.review_id} lacks explicit Tiingo query/series linkage"
            )
        links.append(
            ProviderSeriesLink(
                instrument_id=instrument_id,
                review_id=seed.review_id,
                provider_id="tiingo",
                provider_series_id=tiingo_series,
                query_symbol=tiingo_query,
            )
        )

        observation = observations.get(tiingo_query)
        if observation is None:
            raise ReviewedIdentitySnapshotError(
                f"review seed {seed.review_id} has no matching Tiingo lineage audit observation"
            )
        observed_first = _required_date(
            observation.get("observed_first_date"),
            f"{tiingo_query}.observed_first_date",
        )
        predecessor = _known_predecessor_symbol(observation)
        gaps.extend(
            _coverage_gaps_for_seed(
                seed=seed,
                instrument_id=instrument_id,
                observed_first=observed_first,
                predecessor=predecessor,
            )
        )
        evidence.update(_audit_evidence_refs(observation))

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
            sorted(gaps, key=lambda item: (str(item.instrument_id), item.gap_start, item.gap_end))
        ),
        evidence_refs=tuple(sorted(evidence)),
    )


def persist_reviewed_identity_snapshot_candidate(
    path: Path,
    candidate: ReviewedIdentitySnapshotCandidate,
) -> None:
    """Persist a metadata-only candidate atomically; no raw provider prices are included."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _candidate_payload(candidate)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_reviewed_identity_snapshot_candidate(path: Path) -> ReviewedIdentitySnapshotCandidate:
    """Reload a persisted candidate and revalidate its identity/history structure."""

    payload = _decode_object(_read_bytes(path, "reviewed identity candidate"), "candidate")
    if payload.get("schema_version") != "reviewed-identity-candidate-v0.1":
        raise ReviewedIdentitySnapshotError("unsupported reviewed identity candidate schema")

    instruments_raw = payload.get("instruments")
    history_raw = payload.get("symbol_history")
    links_raw = payload.get("provider_series_links")
    gaps_raw = payload.get("coverage_gaps")
    if not isinstance(instruments_raw, list):
        raise ReviewedIdentitySnapshotError("candidate instruments must be an array")
    if not isinstance(history_raw, list):
        raise ReviewedIdentitySnapshotError("candidate symbol_history must be an array")
    if not isinstance(links_raw, list):
        raise ReviewedIdentitySnapshotError("candidate provider_series_links must be an array")
    if not isinstance(gaps_raw, list):
        raise ReviewedIdentitySnapshotError("candidate coverage_gaps must be an array")

    instruments = tuple(_instrument_from_payload(item) for item in instruments_raw)
    history = tuple(_history_from_payload(item) for item in history_raw)
    links = tuple(_link_from_payload(item) for item in links_raw)
    gaps = tuple(_gap_from_payload(item) for item in gaps_raw)
    _validate_loaded_candidate(instruments, history, links, gaps)

    evidence_refs = _text_tuple(payload.get("evidence_refs"), "evidence_refs", allow_empty=True)
    return ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version=_required_text(payload.get("snapshot_version"), "snapshot_version"),
        primary_provider_id=_required_text(
            payload.get("primary_provider_id"), "primary_provider_id"
        ),
        identity_definition_version=_required_text(
            payload.get("identity_definition_version"), "identity_definition_version"
        ),
        symbol_history_definition_version=_required_text(
            payload.get("symbol_history_definition_version"),
            "symbol_history_definition_version",
        ),
        identity_seed_sha256=_sha256_text(
            payload.get("identity_seed_sha256"), "identity_seed_sha256"
        ),
        lineage_audit_sha256=_sha256_text(
            payload.get("lineage_audit_sha256"), "lineage_audit_sha256"
        ),
        instruments=instruments,
        symbol_history=history,
        provider_series_links=links,
        coverage_gaps=gaps,
        evidence_refs=evidence_refs,
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


def _parse_seed(raw: object, primary_provider_id: str) -> ReviewedIdentitySeed:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError("reviewed identity seed must be an object")
    review_id = _required_text(raw.get("review_id"), "review_id")
    provider_links = _text_mapping(raw.get("provider_links"), "provider_links")
    provider_queries = _text_mapping(
        raw.get("provider_query_symbols"), "provider_query_symbols"
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
            f"seed {review_id} cannot use the current ticker itself as the stable Tiingo series ID"
        )

    intervals_raw = raw.get("symbol_history")
    if not isinstance(intervals_raw, list) or not intervals_raw:
        raise ReviewedIdentitySnapshotError(f"seed {review_id} requires reviewed symbol history")
    intervals = tuple(_parse_interval(item, review_id) for item in intervals_raw)
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


def _parse_interval(raw: object, review_id: str) -> ReviewedSymbolInterval:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError(f"symbol-history entry for {review_id} must be an object")
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


def _validate_seed_set(seeds: tuple[ReviewedIdentitySeed, ...]) -> None:
    review_ids: set[str] = set()
    provider_owners: dict[tuple[str, str], str] = {}
    query_owners: dict[tuple[str, str], str] = {}
    for seed in seeds:
        if seed.review_id in review_ids:
            raise ReviewedIdentitySnapshotError(f"duplicate review_id {seed.review_id}")
        review_ids.add(seed.review_id)
        for provider_id, provider_series_id in seed.provider_links.items():
            key = (provider_id, provider_series_id)
            prior = provider_owners.get(key)
            if prior is not None and prior != seed.review_id:
                raise ReviewedIdentitySnapshotError(
                    f"provider series {provider_id}:{provider_series_id} has multiple owners"
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
    for previous, current in zip(ordered, ordered[1:], strict=False):
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
    earliest = intervals[0].effective_from
    tiingo_query = seed.provider_query_symbols["tiingo"]
    gaps: list[IdentityCoverageGap] = []
    if observed_first < earliest:
        gaps.append(
            IdentityCoverageGap(
                instrument_id=instrument_id,
                review_id=seed.review_id,
                provider_id="tiingo",
                query_symbol=tiingo_query,
                gap_start=observed_first,
                gap_end=earliest - timedelta(days=1),
                reason="PREHISTORY_SYMBOL_START_UNRESOLVED",
                known_predecessor_symbol=predecessor,
            )
        )
    for previous, current in zip(intervals, intervals[1:], strict=False):
        if previous.effective_to is None:
            break
        expected_next = previous.effective_to + timedelta(days=1)
        if current.effective_from > expected_next:
            gaps.append(
                IdentityCoverageGap(
                    instrument_id=instrument_id,
                    review_id=seed.review_id,
                    provider_id="tiingo",
                    query_symbol=tiingo_query,
                    gap_start=expected_next,
                    gap_end=current.effective_from - timedelta(days=1),
                    reason="DATED_SYMBOL_HISTORY_GAP",
                    known_predecessor_symbol=None,
                )
            )
    return tuple(gaps)


def _index_audit_observations(raw: list[object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ReviewedIdentitySnapshotError("lineage audit observation must be an object")
        symbol = _required_text(item.get("source_symbol"), "source_symbol")
        if symbol in result:
            raise ReviewedIdentitySnapshotError(f"duplicate lineage audit observation: {symbol}")
        result[symbol] = item
    return result


def _known_predecessor_symbol(observation: Mapping[str, object]) -> str | None:
    raw_events = observation.get("lineage_events")
    if not isinstance(raw_events, list):
        return None
    dated: list[tuple[date, str | None]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        raw_date = event.get("effective_date")
        try:
            effective = _required_date(raw_date, "effective_date")
        except ReviewedIdentitySnapshotError:
            continue
        from_symbol = event.get("from_symbol")
        dated.append((effective, from_symbol if isinstance(from_symbol, str) else None))
    if not dated:
        return None
    return sorted(dated, key=lambda item: item[0])[0][1]


def _audit_evidence_refs(observation: Mapping[str, object]) -> set[str]:
    refs: set[str] = set()
    raw_events = observation.get("lineage_events")
    if not isinstance(raw_events, list):
        return refs
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        value = event.get("source_url")
        if isinstance(value, str) and value.strip():
            refs.add(value.strip())
    return refs


def _validate_candidate_history(history: tuple[SymbolHistoryRecord, ...]) -> None:
    by_instrument: dict[InstrumentId, list[SymbolHistoryRecord]] = {}
    for record in history:
        by_instrument.setdefault(record.instrument_id, []).append(record)
    for instrument_id, records in by_instrument.items():
        ordered = sorted(records, key=lambda item: item.effective_from)
        for previous, current in zip(ordered, ordered[1:], strict=False):
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
        "security_type": str(item.security_type),
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


def _instrument_from_payload(raw: object) -> InstrumentRecord:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError("candidate instrument entry must be an object")
    provider_ids = _text_mapping(raw.get("provider_ids"), "provider_ids")
    try:
        security_type = SecurityType(_required_text(raw.get("security_type"), "security_type"))
    except ValueError as exc:
        raise ReviewedIdentitySnapshotError("candidate instrument has invalid security_type") from exc
    return InstrumentRecord(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        primary_symbol=_required_text(raw.get("primary_symbol"), "primary_symbol"),
        name=_required_text(raw.get("name"), "name"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        security_type=security_type,
        currency=_required_text(raw.get("currency"), "currency"),
        first_trade_date=_optional_date(raw.get("first_trade_date"), "first_trade_date"),
        delisting_date=_optional_date(raw.get("delisting_date"), "delisting_date"),
        provider_ids=MappingProxyType(provider_ids),
    )


def _history_from_payload(raw: object) -> SymbolHistoryRecord:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError("candidate symbol-history entry must be an object")
    return SymbolHistoryRecord(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        symbol=_required_text(raw.get("symbol"), "symbol"),
        exchange=_required_text(raw.get("exchange"), "exchange"),
        effective_from=_required_date(raw.get("effective_from"), "effective_from"),
        effective_to=_optional_date(raw.get("effective_to"), "effective_to"),
    )


def _link_from_payload(raw: object) -> ProviderSeriesLink:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError("candidate provider-series link must be an object")
    return ProviderSeriesLink(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        review_id=_required_text(raw.get("review_id"), "review_id"),
        provider_id=_required_text(raw.get("provider_id"), "provider_id"),
        provider_series_id=_required_text(raw.get("provider_series_id"), "provider_series_id"),
        query_symbol=_required_text(raw.get("query_symbol"), "query_symbol"),
    )


def _gap_from_payload(raw: object) -> IdentityCoverageGap:
    if not isinstance(raw, dict):
        raise ReviewedIdentitySnapshotError("candidate coverage gap must be an object")
    predecessor = raw.get("known_predecessor_symbol")
    if predecessor is not None and not isinstance(predecessor, str):
        raise ReviewedIdentitySnapshotError("known_predecessor_symbol must be text or null")
    return IdentityCoverageGap(
        instrument_id=InstrumentId(_required_text(raw.get("instrument_id"), "instrument_id")),
        review_id=_required_text(raw.get("review_id"), "review_id"),
        provider_id=_required_text(raw.get("provider_id"), "provider_id"),
        query_symbol=_required_text(raw.get("query_symbol"), "query_symbol"),
        gap_start=_required_date(raw.get("gap_start"), "gap_start"),
        gap_end=_required_date(raw.get("gap_end"), "gap_end"),
        reason=_required_text(raw.get("reason"), "reason"),
        known_predecessor_symbol=predecessor,
    )


def _validate_loaded_candidate(
    instruments: tuple[InstrumentRecord, ...],
    history: tuple[SymbolHistoryRecord, ...],
    links: tuple[ProviderSeriesLink, ...],
    gaps: tuple[IdentityCoverageGap, ...],
) -> None:
    if not instruments:
        raise ReviewedIdentitySnapshotError("reviewed identity candidate must not be empty")
    ids = {item.instrument_id for item in instruments}
    if len(ids) != len(instruments):
        raise ReviewedIdentitySnapshotError("candidate contains duplicate instrument IDs")
    _validate_candidate_history(history)
    if any(item.instrument_id not in ids for item in history):
        raise ReviewedIdentitySnapshotError("symbol history references unknown candidate instrument")
    if any(item.instrument_id not in ids for item in links):
        raise ReviewedIdentitySnapshotError("provider series link references unknown instrument")
    if any(item.instrument_id not in ids for item in gaps):
        raise ReviewedIdentitySnapshotError("coverage gap references unknown instrument")
    link_keys = {(item.provider_id, item.query_symbol) for item in links}
    if len(link_keys) != len(links):
        raise ReviewedIdentitySnapshotError("candidate contains duplicate provider query links")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ReviewedIdentitySnapshotError(f"cannot read {label}: {path}") from exc


def _decode_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewedIdentitySnapshotError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ReviewedIdentitySnapshotError(f"{label} root must be an object")
    return payload


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedIdentitySnapshotError(f"{field} must be non-empty text")
    return value.strip()


def _text_mapping(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ReviewedIdentitySnapshotError(f"{field} must be a non-empty object")
    result: dict[str, str] = {}
    for key, item in value.items():
        result[_required_text(key, field)] = _required_text(item, field)
    return result


def _text_tuple(value: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
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
    text = _required_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text.lower()):
        raise ReviewedIdentitySnapshotError(f"{field} must be a SHA-256 hex digest")
    return text.lower()
