"""Extended fail-closed SEC identity resolution for the remaining Tiingo deferrals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.data.auto_identity_import import (
    AutoIdentityEvidence,
    AutoIdentityImportError,
    SecIdentityClient,
    _EXCHANGE_TERMS,
    _SecCompany,
    _SecFiling,
    _contains_exact_start,
    _normalize,
    _ticker_exchange_cooccur,
)
from trade_scout.data.deferred_identity_resolution import _load_all_filing_forms

_EXTENDED_FORMS = frozenset(
    {
        "8-A",
        "8-A12B",
        "8-A12G",
        "10",
        "10-12B",
        "10-12G",
        "10-K",
        "10-K405",
        "10-KSB",
        "10-Q",
        "10-QSB",
        "20-F",
        "40-F",
        "8-K",
        "8-K/A",
        "DEF 14A",
        "S-1",
        "S-1/A",
        "S-2",
        "S-3",
        "S-4",
        "424B1",
        "424B2",
        "424B3",
        "424B4",
        "424B5",
    }
)
_LOOKBACK_DAYS = 2200
_LOOKAHEAD_DAYS = 1100


@dataclass(frozen=True, slots=True)
class ExtendedIdentityResolution:
    source_symbol: str
    observed_first_date: date
    status: str
    resolution_kind: str
    cik: int
    company_name: str
    exchange: str
    evidence_url: str | None
    evidence_title: str | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def as_ready_evidence(self) -> AutoIdentityEvidence:
        if not self.ready or self.evidence_url is None:
            raise AutoIdentityImportError("extended identity resolution is not READY")
        return AutoIdentityEvidence(
            source_symbol=self.source_symbol,
            observed_first_date=self.observed_first_date,
            cik=self.cik,
            company_name=self.company_name,
            exchange=self.exchange,
            source_url=self.evidence_url,
            source_title=self.evidence_title,
            evidence_kind=self.resolution_kind,
            ready=True,
            reason=self.reason,
        )


def resolve_extended_sec_identity(
    *,
    client: SecIdentityClient,
    company: _SecCompany,
    source_symbol: str,
    observed_first_date: date,
) -> ExtendedIdentityResolution:
    """Use broader SEC filing forms and windows without relaxing identity proof requirements."""

    symbol = source_symbol.strip().upper()
    terms = _EXCHANGE_TERMS.get(company.exchange)
    if terms is None:
        return _deferred(company, symbol, observed_first_date, "UNSUPPORTED_EXCHANGE")

    filings = tuple(
        item
        for item in _load_all_filing_forms(client, company.cik)
        if item.form.upper() in _EXTENDED_FORMS
        and observed_first_date - timedelta(days=_LOOKBACK_DAYS)
        <= item.filing_date
        <= observed_first_date + timedelta(days=_LOOKAHEAD_DAYS)
    )

    exact = _find_exact_start_any_form(
        client=client,
        company=company,
        filings=filings,
        observed_first_date=observed_first_date,
    )
    if exact is not None:
        return _ready(
            company,
            symbol,
            observed_first_date,
            exact,
            "EXTENDED_SEC_EXACT_PUBLIC_TRADING_START",
            "broader SEC registration/issuer filing set independently confirms the exact provider-history start",
        )

    pre = _find_ticker_exchange_filing(
        client=client,
        company=company,
        filings=filings,
        boundary=observed_first_date,
        before=True,
    )
    if pre is not None:
        post = _find_ticker_exchange_filing(
            client=client,
            company=company,
            filings=filings,
            boundary=observed_first_date,
            before=False,
        )
        kind = "EXTENDED_SEC_BRACKETED_CONTINUITY" if post is not None else "EXTENDED_SEC_PRE_BOUNDARY_CONTINUITY"
        reason = (
            "broader SEC filing set proves that the same current CIK reported the same ticker and exchange before the provider-history boundary"
        )
        if post is not None:
            reason += "; post-boundary SEC evidence independently brackets continuity"
        return _ready(company, symbol, observed_first_date, pre, kind, reason)

    return _deferred(
        company,
        symbol,
        observed_first_date,
        "EXTENDED_SEC_BOUNDARY_NOT_PROVEN",
        "broader SEC registration/issuer filing review still does not prove same-CIK ticker/exchange continuity before the provider-history boundary",
    )


def _find_exact_start_any_form(
    *, client: SecIdentityClient, company: _SecCompany, filings: tuple[_SecFiling, ...], observed_first_date: date
) -> _SecFiling | None:
    for filing in sorted(filings, key=lambda item: abs((item.filing_date - observed_first_date).days)):
        try:
            text = _normalize(client.get_text(filing.source_url))
        except AutoIdentityImportError:
            continue
        if _contains_exact_start(text, company.ticker, observed_first_date):
            return filing
    return None


def _find_ticker_exchange_filing(
    *, client: SecIdentityClient, company: _SecCompany, filings: tuple[_SecFiling, ...], boundary: date, before: bool
) -> _SecFiling | None:
    terms = _EXCHANGE_TERMS[company.exchange]
    candidates = [item for item in filings if item.filing_date <= boundary] if before else [item for item in filings if item.filing_date >= boundary]
    candidates.sort(key=lambda item: abs((item.filing_date - boundary).days))
    for filing in candidates:
        try:
            text = _normalize(client.get_text(filing.source_url))
        except AutoIdentityImportError:
            continue
        if _ticker_exchange_cooccur(text, company.ticker, terms):
            return filing
    return None


def _ready(
    company: _SecCompany,
    symbol: str,
    observed_first_date: date,
    filing: _SecFiling,
    kind: str,
    reason: str,
) -> ExtendedIdentityResolution:
    return ExtendedIdentityResolution(
        source_symbol=symbol,
        observed_first_date=observed_first_date,
        status="READY",
        resolution_kind=kind,
        cik=company.cik,
        company_name=company.name,
        exchange=company.exchange,
        evidence_url=filing.source_url,
        evidence_title=f"SEC {filing.form} filed {filing.filing_date.isoformat()}",
        reason=reason,
    )


def _deferred(
    company: _SecCompany,
    symbol: str,
    observed_first_date: date,
    kind: str,
    reason: str = "extended SEC evidence is insufficient",
) -> ExtendedIdentityResolution:
    return ExtendedIdentityResolution(
        source_symbol=symbol,
        observed_first_date=observed_first_date,
        status="DEFERRED",
        resolution_kind=kind,
        cik=company.cik,
        company_name=company.name,
        exchange=company.exchange,
        evidence_url=None,
        evidence_title=None,
        reason=reason,
    )


__all__ = ["ExtendedIdentityResolution", "resolve_extended_sec_identity"]
