"""Historical SEC full-index evidence for pre-1996 identity boundaries.

SEC documents that the EDGAR full/quarterly indexes are available from 1994Q3 onward.  This
module uses those primary-source indexes to recover filings that may not be discoverable through
our submissions-based resolver, then inspects the original filing text for ticker/exchange
continuity.  It is fail-closed: absence of evidence is never treated as approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.auto_identity_import import (
    AutoIdentityImportError,
    SecIdentityClient,
    _EXCHANGE_TERMS,
    _SecCompany,
    _normalize,
    _ticker_exchange_cooccur,
)

_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
_ARCHIVE_URL = "https://www.sec.gov/Archives/{filename}"
_EARLIEST_INDEX_DATE = date(1994, 7, 1)


@dataclass(frozen=True, slots=True)
class HistoricalIndexFiling:
    cik: int
    company_name: str
    form: str
    filing_date: date
    filename: str

    @property
    def source_url(self) -> str:
        return _ARCHIVE_URL.format(filename=self.filename.lstrip("/"))


@dataclass(frozen=True, slots=True)
class HistoricalBoundaryEvidence:
    symbol: str
    cik: int
    status: str
    kind: str
    pre_boundary_url: str | None
    post_boundary_url: str | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "READY"


def load_full_index_window(
    client: SecIdentityClient,
    *,
    start: date,
    end: date,
) -> tuple[HistoricalIndexFiling, ...]:
    """Load SEC master-index rows whose filing date falls in the requested window."""

    if end < start:
        raise ValueError("historical SEC index end must not precede start")
    if end < _EARLIEST_INDEX_DATE:
        return ()
    rows: list[HistoricalIndexFiling] = []
    for year, quarter in _quarters(max(start, _EARLIEST_INDEX_DATE), end):
        text = client.get_text(_INDEX_URL.format(year=year, quarter=quarter))
        rows.extend(_parse_master_index(text, start=start, end=end))
    unique = {(r.cik, r.filing_date, r.form, r.filename): r for r in rows}
    return tuple(sorted(unique.values(), key=lambda r: (r.filing_date, r.cik, r.form, r.filename)))


def resolve_historical_campaign_boundary(
    *,
    client: SecIdentityClient,
    company: _SecCompany,
    boundary: date,
    index_rows: tuple[HistoricalIndexFiling, ...],
    max_documents_per_side: int = 12,
) -> HistoricalBoundaryEvidence:
    """Prove same-CIK ticker/exchange continuity across a campaign truncation boundary."""

    terms = _EXCHANGE_TERMS.get(company.exchange)
    if terms is None:
        return _deferred(company, "UNSUPPORTED_EXCHANGE", "exchange is unsupported")

    company_rows = [row for row in index_rows if row.cik == company.cik]
    pre = sorted((r for r in company_rows if r.filing_date <= boundary), key=lambda r: r.filing_date, reverse=True)
    post = sorted((r for r in company_rows if r.filing_date >= boundary), key=lambda r: r.filing_date)

    pre_match = _first_match(client, company, terms, pre[:max_documents_per_side])
    if pre_match is None:
        if not pre:
            return _deferred(company, "NO_PRE_BOUNDARY_INDEX_FILING", "SEC full index contains no same-CIK filing before the campaign boundary")
        return _deferred(company, "PRE_BOUNDARY_INDEX_NO_TICKER_EXCHANGE", "same-CIK pre-boundary SEC filings exist but none proves the same ticker/exchange")

    post_match = _first_match(client, company, terms, post[:max_documents_per_side])
    kind = "SEC_FULL_INDEX_BRACKETED_CONTINUITY" if post_match is not None else "SEC_FULL_INDEX_PRE_BOUNDARY_CONTINUITY"
    reason = "SEC full-index filing before the dataset truncation boundary proves the same registrant, ticker, and exchange"
    if post_match is not None:
        reason += "; a post-boundary SEC filing independently brackets continuity"
    return HistoricalBoundaryEvidence(
        symbol=company.ticker,
        cik=company.cik,
        status="READY",
        kind=kind,
        pre_boundary_url=pre_match.source_url,
        post_boundary_url=post_match.source_url if post_match is not None else None,
        reason=reason,
    )


def _first_match(
    client: SecIdentityClient,
    company: _SecCompany,
    terms: tuple[str, ...],
    rows: list[HistoricalIndexFiling],
) -> HistoricalIndexFiling | None:
    for row in rows:
        try:
            text = _normalize(client.get_text(row.source_url))
        except AutoIdentityImportError:
            continue
        if _ticker_exchange_cooccur(text, company.ticker, terms):
            return row
    return None


def _parse_master_index(text: str, *, start: date, end: date) -> list[HistoricalIndexFiling]:
    result: list[HistoricalIndexFiling] = []
    for raw in text.splitlines():
        parts = raw.split("|")
        if len(parts) != 5 or not parts[0].strip().isdigit():
            continue
        try:
            filing_date = date.fromisoformat(parts[3].strip())
        except ValueError:
            continue
        if not (start <= filing_date <= end):
            continue
        result.append(HistoricalIndexFiling(int(parts[0]), parts[1].strip(), parts[2].strip(), filing_date, parts[4].strip()))
    return result


def _quarters(start: date, end: date) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    year, quarter = start.year, (start.month - 1) // 3 + 1
    end_key = (end.year, (end.month - 1) // 3 + 1)
    while (year, quarter) <= end_key:
        out.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return tuple(out)


def _deferred(company: _SecCompany, kind: str, reason: str) -> HistoricalBoundaryEvidence:
    return HistoricalBoundaryEvidence(company.ticker, company.cik, "DEFERRED", kind, None, None, reason)


__all__ = [
    "HistoricalBoundaryEvidence",
    "HistoricalIndexFiling",
    "load_full_index_window",
    "resolve_historical_campaign_boundary",
]
