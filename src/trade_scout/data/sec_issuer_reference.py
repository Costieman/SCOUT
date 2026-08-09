"""Project reviewed SEC links into issuer references without changing security identity."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from trade_scout.data.contracts import InstrumentId, InstrumentRecord
from trade_scout.data.provider import ProviderInstrument


@dataclass(frozen=True, slots=True)
class SecIssuerReference:
    """Issuer-level SEC metadata linked to an existing canonical security after identity review."""

    instrument_id: InstrumentId
    cik: int
    sec_provider_instrument_id: str
    current_ticker: str
    current_exchange: str
    issuer_name: str


@dataclass(frozen=True, slots=True)
class UnresolvedSecIssuerReference:
    """SEC row that cannot be associated with a canonical security without further review."""

    sec_provider_instrument_id: str
    cik: int
    ticker: str
    exchange: str
    issuer_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class SecIssuerReferenceProjection:
    """Resolved issuer references plus rows deliberately kept outside canonical identity."""

    resolved: tuple[SecIssuerReference, ...]
    unresolved: tuple[UnresolvedSecIssuerReference, ...]


def project_reviewed_sec_issuer_references(
    instruments: Iterable[InstrumentRecord],
    sec_records: Iterable[ProviderInstrument],
) -> SecIssuerReferenceProjection:
    """Attach SEC issuer metadata only through an already-reviewed exact provider link.

    This function never matches on ticker, exchange, company name, or CIK. A canonical instrument
    must already contain the exact ``sec_edgar`` provider identity created through the identity
    review boundary. CIK remains issuer metadata and is never used as the canonical security key.
    """

    canonical = tuple(instruments)
    by_sec_id: dict[str, list[InstrumentRecord]] = {}
    for instrument in canonical:
        sec_id = instrument.provider_ids.get("sec_edgar")
        if sec_id is not None:
            by_sec_id.setdefault(sec_id, []).append(instrument)

    resolved: list[SecIssuerReference] = []
    unresolved: list[UnresolvedSecIssuerReference] = []
    seen_sec_ids: set[str] = set()
    for record in sec_records:
        if record.provider_id != "sec_edgar":
            raise ValueError("SEC issuer projection accepts only sec_edgar provider records")
        if record.provider_instrument_id in seen_sec_ids:
            raise ValueError("SEC issuer projection requires unique provider instrument identities")
        seen_sec_ids.add(record.provider_instrument_id)
        cik = _cik(record)
        matches = by_sec_id.get(record.provider_instrument_id, [])
        if len(matches) == 1:
            resolved.append(
                SecIssuerReference(
                    instrument_id=matches[0].instrument_id,
                    cik=cik,
                    sec_provider_instrument_id=record.provider_instrument_id,
                    current_ticker=record.symbol,
                    current_exchange=record.exchange,
                    issuer_name=record.name,
                )
            )
            continue
        reason = (
            "no reviewed canonical SEC provider link"
            if not matches
            else "SEC provider identity maps to multiple canonical instruments"
        )
        unresolved.append(
            UnresolvedSecIssuerReference(
                sec_provider_instrument_id=record.provider_instrument_id,
                cik=cik,
                ticker=record.symbol,
                exchange=record.exchange,
                issuer_name=record.name,
                reason=reason,
            )
        )

    return SecIssuerReferenceProjection(
        resolved=tuple(sorted(resolved, key=lambda item: str(item.instrument_id))),
        unresolved=tuple(
            sorted(unresolved, key=lambda item: (item.sec_provider_instrument_id, item.ticker))
        ),
    )


def _cik(record: ProviderInstrument) -> int:
    value = record.source_fields.get("cik")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("SEC provider record requires a positive integer issuer CIK")
    return value
