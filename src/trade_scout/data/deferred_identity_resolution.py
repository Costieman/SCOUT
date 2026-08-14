"""Resolve conservative Tiingo identity deferrals without guessing.

The first automatic identity pass intentionally required either an exact public-trading start or
bounded campaign continuity. This module re-examines the resulting deferred queue. It may advance
only cases where SEC primary-source filings prove that the current registrant already owned and
reported the same trading symbol/exchange before the provider history begins. Structural anomalies,
legacy lineage cases, CIK changes, unsupported exchanges, and unresolved boundaries remain deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

from trade_scout.data.auto_identity_import import (
    AutoIdentityEvidence,
    AutoIdentityImportError,
    SecIdentityClient,
    _EXCHANGE_TERMS,
    _SecCompany,
    _SecFiling,
    _find_exact_start,
    _load_all_filings,
    _normalize,
    _ticker_exchange_cooccur,
)

_PRE_BOUNDARY_LOOKBACK_DAYS = 800
_POST_BOUNDARY_LOOKAHEAD_DAYS = 550


@dataclass(frozen=True, slots=True)
class DeferredIdentityResolution:
    """One auditable second-pass identity-boundary decision."""

    source_symbol: str
    observed_first_date: date
    original_evidence_kind: str
    original_reason: str
    status: str
    resolution_kind: str
    cik: int | None
    company_name: str | None
    exchange: str | None
    evidence_url: str | None
    evidence_title: str | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def as_ready_evidence(self) -> AutoIdentityEvidence:
        """Convert an approved resolution to the existing candidate-builder contract."""

        if not self.ready:
            raise AutoIdentityImportError("deferred resolution is not READY")
        if self.cik is None or self.company_name is None or self.exchange is None:
            raise AutoIdentityImportError("READY deferred resolution lacks SEC identity fields")
        if self.evidence_url is None:
            raise AutoIdentityImportError("READY deferred resolution lacks primary-source evidence")
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


def resolve_deferred_identity(
    *,
    client: SecIdentityClient,
    catalog: Mapping[str, _SecCompany],
    evidence: AutoIdentityEvidence,
    protected_symbols: frozenset[str] = frozenset(),
) -> DeferredIdentityResolution:
    """Resolve one deferred symbol only when a stronger SEC boundary proof exists."""

    symbol = evidence.source_symbol.strip().upper()
    if symbol in protected_symbols:
        return _deferred(
            evidence,
            "LEGACY_LINEAGE_PROTECTED",
            "symbol has an existing dedicated lineage deferral and is excluded from bulk automation",
        )
    if evidence.evidence_kind == "STRUCTURAL_ANOMALY":
        return _deferred(
            evidence,
            "STRUCTURAL_ANOMALY",
            "provider structural anomaly must be resolved before identity automation",
        )

    company = _catalog_company(catalog, symbol)
    if company is None:
        return _deferred(
            evidence,
            "NO_SEC_TICKER_MATCH",
            "no unique current SEC ticker match, including dot/hyphen share-class aliases",
        )
    if evidence.cik is not None and evidence.cik != company.cik:
        return _deferred(
            evidence,
            "SEC_CIK_CHANGED",
            f"checkpoint CIK {evidence.cik:010d} differs from current SEC CIK {company.cik:010d}",
            company=company,
        )
    if company.exchange not in _EXCHANGE_TERMS:
        return _deferred(
            evidence,
            "UNSUPPORTED_EXCHANGE",
            f"SEC exchange {company.exchange!r} is not supported by the equity identity resolver",
            company=company,
        )

    try:
        filings = _load_all_filings(client, company.cik)
    except AutoIdentityImportError as exc:
        return _deferred(evidence, "SEC_SOURCE_ERROR", str(exc), company=company)

    exact = _find_exact_start(
        client=client,
        company=company,
        filings=filings,
        observed_first_date=evidence.observed_first_date,
    )
    if exact is not None:
        return DeferredIdentityResolution(
            source_symbol=symbol,
            observed_first_date=evidence.observed_first_date,
            original_evidence_kind=evidence.evidence_kind,
            original_reason=evidence.reason,
            status="READY",
            resolution_kind="EXACT_PUBLIC_TRADING_START",
            cik=company.cik,
            company_name=company.name,
            exchange=company.exchange,
            evidence_url=exact.source_url,
            evidence_title=exact.source_title,
            reason="second-pass SEC review independently confirms the exact provider-history start",
        )

    pre = _nearest_ticker_exchange_filing(
        client=client,
        company=company,
        filings=filings,
        boundary=evidence.observed_first_date,
        before=True,
    )
    if pre is not None:
        post = _nearest_ticker_exchange_filing(
            client=client,
            company=company,
            filings=filings,
            boundary=evidence.observed_first_date,
            before=False,
        )
        kind = (
            "BRACKETED_PRE_BOUNDARY_CONTINUITY"
            if post is not None
            else "ESTABLISHED_PRE_BOUNDARY_CONTINUITY"
        )
        detail = (
            "SEC annual filing before the provider-history boundary proves that the same registrant "
            "already reported the same ticker and exchange"
        )
        if post is not None:
            detail += "; a near-boundary filing after the start independently brackets continuity"
        return DeferredIdentityResolution(
            source_symbol=symbol,
            observed_first_date=evidence.observed_first_date,
            original_evidence_kind=evidence.evidence_kind,
            original_reason=evidence.reason,
            status="READY",
            resolution_kind=kind,
            cik=company.cik,
            company_name=company.name,
            exchange=company.exchange,
            evidence_url=pre.source_url,
            evidence_title=f"SEC {pre.form} filed {pre.filing_date.isoformat()}",
            reason=detail,
        )

    post = _nearest_ticker_exchange_filing(
        client=client,
        company=company,
        filings=filings,
        boundary=evidence.observed_first_date,
        before=False,
    )
    if post is not None:
        return _deferred(
            evidence,
            "POST_BOUNDARY_ONLY",
            "same registrant/ticker/exchange is evidenced only after the provider start; this does not prove the earlier boundary",
            company=company,
            filing=post,
        )

    return _deferred(
        evidence,
        "BOUNDARY_NOT_PROVEN",
        "no qualifying SEC filing proves same-registrant ticker/exchange continuity before the provider-history start",
        company=company,
    )


def _catalog_company(
    catalog: Mapping[str, _SecCompany],
    source_symbol: str,
) -> _SecCompany | None:
    candidates = _symbol_aliases(source_symbol)
    matches = {catalog[key] for key in candidates if key in catalog}
    if len(matches) != 1:
        return None
    return next(iter(matches))


def _symbol_aliases(source_symbol: str) -> tuple[str, ...]:
    symbol = source_symbol.strip().upper()
    aliases = {symbol}
    if "." in symbol:
        aliases.add(symbol.replace(".", "-"))
    if "-" in symbol:
        aliases.add(symbol.replace("-", "."))
    return tuple(sorted(aliases))


def _nearest_ticker_exchange_filing(
    *,
    client: SecIdentityClient,
    company: _SecCompany,
    filings: tuple[_SecFiling, ...],
    boundary: date,
    before: bool,
) -> _SecFiling | None:
    terms = _EXCHANGE_TERMS.get(company.exchange)
    if terms is None:
        return None
    lower = boundary - timedelta(days=_PRE_BOUNDARY_LOOKBACK_DAYS)
    upper = boundary + timedelta(days=_POST_BOUNDARY_LOOKAHEAD_DAYS)
    candidates = [
        filing
        for filing in filings
        if lower <= filing.filing_date <= upper
        and ((filing.filing_date <= boundary) if before else (filing.filing_date >= boundary))
    ]
    candidates.sort(
        key=lambda item: abs((item.filing_date - boundary).days)
    )
    for filing in candidates:
        try:
            text = _normalize(client.get_text(filing.source_url))
        except AutoIdentityImportError:
            continue
        if _ticker_exchange_cooccur(text, company.ticker, terms):
            return filing
    return None


def _deferred(
    evidence: AutoIdentityEvidence,
    kind: str,
    reason: str,
    *,
    company: _SecCompany | None = None,
    filing: _SecFiling | None = None,
) -> DeferredIdentityResolution:
    return DeferredIdentityResolution(
        source_symbol=evidence.source_symbol.strip().upper(),
        observed_first_date=evidence.observed_first_date,
        original_evidence_kind=evidence.evidence_kind,
        original_reason=evidence.reason,
        status="DEFERRED",
        resolution_kind=kind,
        cik=company.cik if company is not None else evidence.cik,
        company_name=company.name if company is not None else evidence.company_name,
        exchange=company.exchange if company is not None else evidence.exchange,
        evidence_url=filing.source_url if filing is not None else None,
        evidence_title=(
            f"SEC {filing.form} filed {filing.filing_date.isoformat()}"
            if filing is not None
            else None
        ),
        reason=reason,
    )


__all__ = [
    "DeferredIdentityResolution",
    "resolve_deferred_identity",
]
