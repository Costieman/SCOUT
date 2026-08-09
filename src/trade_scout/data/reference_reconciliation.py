"""Current-reference reconciliation without promoting ticker similarity into identity.

Reference sources such as SEC EDGAR can enrich issuer metadata, but current ticker associations are
not a permanent security master. This module therefore produces review candidates only. It never
links provider identities, rewrites canonical instruments, or back-projects current reference data
into historical universes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.provider import ProviderInstrument


class ReferenceCandidateState(StrEnum):
    """Strength of current-reference evidence without implying canonical identity."""

    EXACT_SYMBOL_EXCHANGE = "EXACT_SYMBOL_EXCHANGE"
    SYMBOL_ONLY = "SYMBOL_ONLY"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


@dataclass(frozen=True, slots=True)
class ReferenceMatchCandidate:
    """One market-provider record and its non-authoritative reference candidates."""

    market_provider_id: str
    market_provider_instrument_id: str
    symbol: str
    exchange: str
    state: ReferenceCandidateState
    reference_provider_ids: tuple[str, ...]
    reference_provider_instrument_ids: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def has_unique_candidate(self) -> bool:
        """Return whether exactly one reference row is suggested for human/system review."""

        return len(self.reference_provider_instrument_ids) == 1 and self.state in {
            ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE,
            ReferenceCandidateState.SYMBOL_ONLY,
        }


class HistoricalReferenceBackProjectionError(ValueError):
    """Raised when current reference associations are applied to a historical market snapshot."""


def reconcile_current_reference_candidates(
    market_records: Iterable[ProviderInstrument],
    reference_records: Iterable[ProviderInstrument],
    *,
    market_as_of: date | None = None,
) -> tuple[ReferenceMatchCandidate, ...]:
    """Generate review candidates using exact current symbol/exchange evidence.

    ``market_as_of`` must be ``None`` because the reference records are assumed to represent a
    current association snapshot. A historical date would silently back-project present-day
    reference metadata and is therefore rejected.

    Symbol text is matched exactly after trimming/case normalization. Punctuation is not rewritten
    because vendor-specific ticker transformations can collapse distinct securities. Exchange text
    is normalized only for case and surrounding whitespace. A unique symbol-only match is retained
    as weaker evidence rather than silently treated as an identity link.
    """

    if market_as_of is not None:
        raise HistoricalReferenceBackProjectionError(
            "current reference associations cannot be reconciled against a historical "
            "market snapshot"
        )

    references = tuple(reference_records)
    by_symbol: dict[str, list[ProviderInstrument]] = defaultdict(list)
    for record in references:
        by_symbol[_normalized_symbol(record.symbol)].append(record)

    result = tuple(
        _candidate_for_market_record(record, by_symbol.get(_normalized_symbol(record.symbol), []))
        for record in market_records
    )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.market_provider_id,
                item.market_provider_instrument_id,
                item.symbol,
            ),
        )
    )


def _candidate_for_market_record(
    market: ProviderInstrument,
    symbol_matches: list[ProviderInstrument],
) -> ReferenceMatchCandidate:
    if not symbol_matches:
        return _candidate(
            market,
            state=ReferenceCandidateState.UNMATCHED,
            matches=(),
            evidence=("no exact current symbol match",),
        )

    exact_exchange = tuple(
        item
        for item in symbol_matches
        if _normalized_exchange(item.exchange) == _normalized_exchange(market.exchange)
    )
    if len(exact_exchange) == 1:
        match = exact_exchange[0]
        evidence = ["exact current symbol match", "exact normalized exchange match"]
        if market.name.strip() and match.name.strip():
            if _normalized_name(market.name) == _normalized_name(match.name):
                evidence.append("normalized name also agrees")
            else:
                evidence.append("name differs; candidate remains non-authoritative")
        else:
            evidence.append("name unavailable on at least one source")
        return _candidate(
            market,
            state=ReferenceCandidateState.EXACT_SYMBOL_EXCHANGE,
            matches=(match,),
            evidence=tuple(evidence),
        )

    if len(exact_exchange) > 1:
        return _candidate(
            market,
            state=ReferenceCandidateState.AMBIGUOUS,
            matches=exact_exchange,
            evidence=("multiple reference rows share exact current symbol and exchange",),
        )

    if len(symbol_matches) == 1:
        return _candidate(
            market,
            state=ReferenceCandidateState.SYMBOL_ONLY,
            matches=tuple(symbol_matches),
            evidence=("exact current symbol match", "exchange does not agree"),
        )

    return _candidate(
        market,
        state=ReferenceCandidateState.AMBIGUOUS,
        matches=tuple(symbol_matches),
        evidence=("multiple reference rows share the current symbol",),
    )


def _candidate(
    market: ProviderInstrument,
    *,
    state: ReferenceCandidateState,
    matches: tuple[ProviderInstrument, ...],
    evidence: tuple[str, ...],
) -> ReferenceMatchCandidate:
    ordered = tuple(
        sorted(matches, key=lambda item: (item.provider_id, item.provider_instrument_id))
    )
    return ReferenceMatchCandidate(
        market_provider_id=market.provider_id,
        market_provider_instrument_id=market.provider_instrument_id,
        symbol=market.symbol,
        exchange=market.exchange,
        state=state,
        reference_provider_ids=tuple(item.provider_id for item in ordered),
        reference_provider_instrument_ids=tuple(item.provider_instrument_id for item in ordered),
        evidence=evidence,
    )


def _normalized_symbol(value: str) -> str:
    return value.strip().upper()


def _normalized_exchange(value: str) -> str:
    return value.strip().upper()


def _normalized_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())
