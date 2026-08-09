"""Conservative reconciliation between Stooq evidence links and SEC issuer references.

The free stack deliberately separates security identity from issuer identity. Stooq query symbols
are explicitly reviewed evidence links; SEC CIK identifies a filer/entity. This module can establish
that a reviewed ticker/exchange claim has a unique current SEC issuer association, but it never
turns that association into a permanent Trade Scout security identifier automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trade_scout.data.providers.sec_edgar import SecTickerAssociation


class FreeStackIdentityState(StrEnum):
    """Result of reconciling one reviewed Stooq claim with current SEC reference data."""

    UNIQUE_ISSUER_REFERENCE = "UNIQUE_ISSUER_REFERENCE"
    NO_SEC_MATCH = "NO_SEC_MATCH"
    AMBIGUOUS_SEC_MATCH = "AMBIGUOUS_SEC_MATCH"


@dataclass(frozen=True, slots=True)
class StooqIdentityClaim:
    """Externally reviewed claim connecting a Stooq query symbol to ticker/exchange text."""

    query_symbol: str
    provider_instrument_id: str
    ticker: str
    exchange: str

    def __post_init__(self) -> None:
        if not self.query_symbol.strip():
            raise ValueError("Stooq query symbol must be non-empty")
        if not self.provider_instrument_id.strip():
            raise ValueError("Stooq provider instrument ID must be non-empty")
        if not self.ticker.strip() or not self.exchange.strip():
            raise ValueError("reviewed ticker and exchange must be non-empty")


@dataclass(frozen=True, slots=True)
class FreeStackIdentityEvidence:
    """Auditable issuer-reference result for one reviewed Stooq security claim."""

    query_symbol: str
    provider_instrument_id: str
    reviewed_ticker: str
    reviewed_exchange: str
    state: FreeStackIdentityState
    sec_ciks: tuple[int, ...]
    sec_names: tuple[str, ...]
    note: str


def reconcile_stooq_claim_with_sec(
    claim: StooqIdentityClaim,
    associations: tuple[SecTickerAssociation, ...],
) -> FreeStackIdentityEvidence:
    """Match only exact current ticker/exchange associations; never fall back to company name."""

    ticker = claim.ticker.strip().upper()
    exchange = claim.exchange.strip().upper()
    matches = tuple(
        item
        for item in associations
        if item.ticker.strip().upper() == ticker and item.exchange.strip().upper() == exchange
    )
    distinct = tuple(sorted({(item.cik, item.name) for item in matches}))

    if not distinct:
        return FreeStackIdentityEvidence(
            query_symbol=claim.query_symbol.upper(),
            provider_instrument_id=claim.provider_instrument_id,
            reviewed_ticker=ticker,
            reviewed_exchange=exchange,
            state=FreeStackIdentityState.NO_SEC_MATCH,
            sec_ciks=(),
            sec_names=(),
            note=(
                "No exact current SEC ticker/exchange association matches the reviewed claim. "
                "No identity inference is made from ticker alone or company-name similarity."
            ),
        )

    ciks = tuple(sorted({cik for cik, _name in distinct}))
    names = tuple(sorted({name for _cik, name in distinct}))
    if len(ciks) != 1:
        return FreeStackIdentityEvidence(
            query_symbol=claim.query_symbol.upper(),
            provider_instrument_id=claim.provider_instrument_id,
            reviewed_ticker=ticker,
            reviewed_exchange=exchange,
            state=FreeStackIdentityState.AMBIGUOUS_SEC_MATCH,
            sec_ciks=ciks,
            sec_names=names,
            note=(
                "Multiple SEC issuer CIKs share the exact reviewed ticker/exchange association. "
                "The claim remains unresolved and must not be linked automatically."
            ),
        )

    return FreeStackIdentityEvidence(
        query_symbol=claim.query_symbol.upper(),
        provider_instrument_id=claim.provider_instrument_id,
        reviewed_ticker=ticker,
        reviewed_exchange=exchange,
        state=FreeStackIdentityState.UNIQUE_ISSUER_REFERENCE,
        sec_ciks=ciks,
        sec_names=names,
        note=(
            "The reviewed Stooq ticker/exchange claim has one current SEC issuer association. "
            "This establishes issuer-reference evidence only: CIK is not a permanent security ID, "
            "and the current association must not be back-projected through history."
        ),
    )
