"""Fail-closed automatic identity evidence and candidate materialization for Tiingo imports.

This module is intentionally narrow. It may advance only provider histories whose durable
structural profile is clean and whose identity boundary is independently supported by SEC
primary-source evidence. Ambiguous histories remain deferred. Canonical promotion is performed
by the existing Tiingo promotion service, not here.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from html import unescape
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from trade_scout.data.contracts import InstrumentRecord, SecurityType, SymbolHistoryRecord
from trade_scout.data.reviewed_identity_snapshot import (
    ProviderSeriesLink,
    ReviewedIdentitySnapshotCandidate,
    derive_reviewed_instrument_id,
)

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{name}"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_ANNUAL_FORMS = frozenset({"10-K", "10-K405", "10-KSB", "20-F", "40-F"})
_EXCHANGE_TO_MIC = {"NYSE": "XNYS", "Nasdaq": "XNAS", "NYSE American": "XASE"}
_EXCHANGE_TERMS = {
    "NYSE": ("new york stock exchange", " nyse "),
    "Nasdaq": ("nasdaq",),
    "NYSE American": ("nyse american", "american stock exchange", "amex"),
}
_TRADING_TERMS = (
    "began trading",
    "commenced trading",
    "started trading",
    "initial public offering",
    "shares began trading",
    "common stock began trading",
    "listed on",
)


class AutoIdentityImportError(RuntimeError):
    """Raised when automatic identity import cannot proceed without guessing."""


@dataclass(frozen=True, slots=True)
class AutoIdentityEvidence:
    """Primary-source evidence sufficient for one conservative automatic decision."""

    source_symbol: str
    observed_first_date: date
    cik: int | None
    company_name: str | None
    exchange: str | None
    source_url: str | None
    source_title: str | None
    evidence_kind: str
    ready: bool
    reason: str


@dataclass(frozen=True, slots=True)
class _SecCompany:
    cik: int
    name: str
    ticker: str
    exchange: str


@dataclass(frozen=True, slots=True)
class _SecFiling:
    cik: int
    form: str
    filing_date: date
    accession_number: str
    primary_document: str

    @property
    def source_url(self) -> str:
        return _ARCHIVES_URL.format(
            cik=self.cik,
            accession=self.accession_number.replace("-", ""),
            document=self.primary_document,
        )


class SecIdentityClient:
    """SEC HTTP client with declared identity, pacing, and bounded retry."""

    def __init__(
        self,
        *,
        user_agent: str,
        minimum_interval_seconds: float = 0.5,
        timeout_seconds: float = 45.0,
        max_attempts: int = 5,
    ) -> None:
        if "@" not in user_agent or not user_agent.strip():
            raise ValueError("SEC user agent must identify the requester and include a contact email")
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        self._headers = {
            "User-Agent": user_agent.strip(),
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
        }
        self._minimum_interval_seconds = minimum_interval_seconds
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._last_request = 0.0

    def get_json(self, url: str) -> object:
        return json.loads(self.get_text(url))

    def get_text(self, url: str) -> str:
        for attempt in range(1, self._max_attempts + 1):
            self._pace()
            request = urllib.request.Request(url, headers=self._headers)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                    payload = response.read()
                    if not isinstance(payload, bytes):
                        raise AutoIdentityImportError("SEC response body is not bytes")
                    return payload.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {403, 429, 500, 502, 503, 504}
                if not retryable or attempt == self._max_attempts:
                    raise AutoIdentityImportError(
                        f"SEC request failed with HTTP {exc.code}: {url}"
                    ) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0**attempt
                time.sleep(delay)
            except OSError as exc:
                if attempt == self._max_attempts:
                    raise AutoIdentityImportError(f"SEC request failed: {url}") from exc
                time.sleep(2.0**attempt)
        raise AssertionError("unreachable SEC retry state")

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request
        remaining = self._minimum_interval_seconds - elapsed
        if self._last_request and remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()


def load_sec_catalog(client: SecIdentityClient) -> Mapping[str, _SecCompany]:
    """Return current SEC ticker/CIK/exchange associations keyed by uppercase ticker."""

    payload = client.get_json(_COMPANY_TICKERS_URL)
    if not isinstance(payload, dict):
        raise AutoIdentityImportError("SEC ticker catalog root must be an object")
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise AutoIdentityImportError("SEC ticker catalog has unsupported structure")
    indexes = {str(value): index for index, value in enumerate(fields)}
    required = {"cik", "name", "ticker", "exchange"}
    if not required.issubset(indexes):
        raise AutoIdentityImportError("SEC ticker catalog is missing required fields")
    result: dict[str, _SecCompany] = {}
    for row in data:
        if not isinstance(row, list):
            continue
        try:
            ticker = str(row[indexes["ticker"]]).strip().upper()
            company = _SecCompany(
                cik=int(row[indexes["cik"]]),
                name=str(row[indexes["name"]]).strip(),
                ticker=ticker,
                exchange=str(row[indexes["exchange"]]).strip(),
            )
        except (IndexError, TypeError, ValueError) as exc:
            raise AutoIdentityImportError("SEC ticker catalog contains malformed row") from exc
        if ticker:
            result[ticker] = company
    return MappingProxyType(result)


def collect_auto_identity_evidence(
    *,
    client: SecIdentityClient,
    catalog: Mapping[str, _SecCompany],
    source_symbol: str,
    observed_first_date: date,
    structural_anomaly_count: int,
    campaign_start: date,
) -> AutoIdentityEvidence:
    """Return READY only for exact-start or bounded same-ticker campaign continuity."""

    symbol = source_symbol.strip().upper()
    if structural_anomaly_count:
        return AutoIdentityEvidence(
            source_symbol=symbol,
            observed_first_date=observed_first_date,
            cik=None,
            company_name=None,
            exchange=None,
            source_url=None,
            source_title=None,
            evidence_kind="STRUCTURAL_ANOMALY",
            ready=False,
            reason=f"provider profile has {structural_anomaly_count} structural anomaly/anomalies",
        )
    company = catalog.get(symbol)
    if company is None:
        return AutoIdentityEvidence(
            source_symbol=symbol,
            observed_first_date=observed_first_date,
            cik=None,
            company_name=None,
            exchange=None,
            source_url=None,
            source_title=None,
            evidence_kind="NO_SEC_TICKER_MATCH",
            ready=False,
            reason="current ticker is absent from the SEC ticker/CIK catalog",
        )
    if company.exchange not in _EXCHANGE_TO_MIC:
        return _deferred(company, observed_first_date, "UNSUPPORTED_EXCHANGE")

    try:
        filings = _load_all_filings(client, company.cik)
    except AutoIdentityImportError as exc:
        return _deferred(company, observed_first_date, "SEC_SOURCE_ERROR", str(exc))

    exact = _find_exact_start(
        client=client,
        company=company,
        filings=filings,
        observed_first_date=observed_first_date,
    )
    if exact is not None:
        return exact

    if observed_first_date == campaign_start:
        continuity = _find_campaign_continuity(
            client=client,
            company=company,
            filings=filings,
            campaign_start=campaign_start,
        )
        if continuity is not None:
            return continuity

    return _deferred(company, observed_first_date, "BOUNDARY_NOT_PROVEN")


def build_auto_reviewed_candidate(
    *,
    existing: ReviewedIdentitySnapshotCandidate,
    ready_evidence: tuple[AutoIdentityEvidence, ...],
) -> ReviewedIdentitySnapshotCandidate:
    """Merge automatically evidenced simple identities into a reviewed candidate."""

    if any(not item.ready for item in ready_evidence):
        raise AutoIdentityImportError("candidate materialization received non-ready evidence")
    existing_queries = {
        (item.provider_id, item.query_symbol.upper()) for item in existing.provider_series_links
    }
    instruments = list(existing.instruments)
    history = list(existing.symbol_history)
    links = list(existing.provider_series_links)
    evidence_refs = set(existing.evidence_refs)

    for evidence in sorted(ready_evidence, key=lambda item: item.source_symbol):
        if evidence.cik is None or evidence.company_name is None or evidence.exchange is None:
            raise AutoIdentityImportError("ready evidence is missing SEC identity fields")
        if evidence.source_url is None:
            raise AutoIdentityImportError("ready evidence is missing its primary-source URL")
        key = ("tiingo", evidence.source_symbol)
        if key in existing_queries:
            continue
        review_id = f"auto-sec-cik-{evidence.cik:010d}"
        instrument_id = derive_reviewed_instrument_id(review_id)
        mic = _EXCHANGE_TO_MIC[evidence.exchange]
        provider_series_id = f"tiingo-series:{review_id}"
        first_trade_date = (
            evidence.observed_first_date
            if evidence.evidence_kind == "EXACT_PUBLIC_TRADING_START"
            else None
        )
        instruments.append(
            InstrumentRecord(
                instrument_id=instrument_id,
                primary_symbol=evidence.source_symbol,
                name=evidence.company_name,
                exchange=mic,
                security_type=SecurityType.COMMON_STOCK,
                currency="USD",
                first_trade_date=first_trade_date,
                delisting_date=None,
                provider_ids=MappingProxyType(
                    {
                        existing.primary_provider_id: review_id,
                        "tiingo": provider_series_id,
                    }
                ),
            )
        )
        history.append(
            SymbolHistoryRecord(
                instrument_id=instrument_id,
                symbol=evidence.source_symbol,
                exchange=mic,
                effective_from=evidence.observed_first_date,
                effective_to=None,
            )
        )
        links.append(
            ProviderSeriesLink(
                instrument_id=instrument_id,
                review_id=review_id,
                provider_id="tiingo",
                provider_series_id=provider_series_id,
                query_symbol=evidence.source_symbol,
            )
        )
        evidence_refs.add(evidence.source_url)
        existing_queries.add(key)

    digest_payload = json.dumps(
        [
            {
                "source_symbol": item.source_symbol,
                "observed_first_date": item.observed_first_date.isoformat(),
                "cik": item.cik,
                "exchange": item.exchange,
                "source_url": item.source_url,
                "evidence_kind": item.evidence_kind,
            }
            for item in sorted(ready_evidence, key=lambda item: item.source_symbol)
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(
        existing.identity_seed_sha256.encode("ascii")
        + existing.lineage_audit_sha256.encode("ascii")
        + digest_payload
    ).hexdigest()

    return ReviewedIdentitySnapshotCandidate(
        schema_version=existing.schema_version,
        snapshot_version=f"tiingo-auto-reviewed-{digest[:16]}",
        primary_provider_id=existing.primary_provider_id,
        identity_definition_version=existing.identity_definition_version,
        symbol_history_definition_version=existing.symbol_history_definition_version,
        identity_seed_sha256=hashlib.sha256(
            existing.identity_seed_sha256.encode("ascii") + digest_payload
        ).hexdigest(),
        lineage_audit_sha256=hashlib.sha256(
            existing.lineage_audit_sha256.encode("ascii") + digest_payload
        ).hexdigest(),
        instruments=tuple(sorted(instruments, key=lambda item: str(item.instrument_id))),
        symbol_history=tuple(
            sorted(
                history,
                key=lambda item: (
                    str(item.instrument_id),
                    item.effective_from,
                    item.symbol,
                ),
            )
        ),
        provider_series_links=tuple(
            sorted(links, key=lambda item: (item.provider_id, item.query_symbol))
        ),
        coverage_gaps=existing.coverage_gaps,
        evidence_refs=tuple(sorted(evidence_refs)),
    )


def candidate_dataset_version(candidate: ReviewedIdentitySnapshotCandidate) -> str:
    """Return a deterministic immutable canonical dataset version for an auto candidate."""

    digest = hashlib.sha256(
        (
            candidate.snapshot_version
            + candidate.identity_seed_sha256
            + candidate.lineage_audit_sha256
        ).encode("ascii")
    ).hexdigest()
    return f"tiingo-reviewed-split-only-auto-{digest[:16]}"


def _deferred(
    company: _SecCompany,
    observed_first_date: date,
    kind: str,
    detail: str | None = None,
) -> AutoIdentityEvidence:
    return AutoIdentityEvidence(
        source_symbol=company.ticker,
        observed_first_date=observed_first_date,
        cik=company.cik,
        company_name=company.name,
        exchange=company.exchange,
        source_url=None,
        source_title=None,
        evidence_kind=kind,
        ready=False,
        reason=detail or "automated evidence does not prove the provider-history identity boundary",
    )


def _load_all_filings(client: SecIdentityClient, cik: int) -> tuple[_SecFiling, ...]:
    payload = client.get_json(_SUBMISSIONS_URL.format(cik=cik))
    if not isinstance(payload, dict):
        raise AutoIdentityImportError("SEC submissions root must be an object")
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        raise AutoIdentityImportError("SEC submissions are missing filings")
    result = list(_filings_from_arrays(cik, filings.get("recent")))
    historical = filings.get("files", [])
    if not isinstance(historical, list):
        raise AutoIdentityImportError("SEC historical submissions list is malformed")
    for item in historical:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise AutoIdentityImportError("SEC historical submissions entry is malformed")
        old_payload = client.get_json(_SUBMISSIONS_FILE_URL.format(name=item["name"]))
        result.extend(_filings_from_arrays(cik, old_payload))
    unique = {
        (item.accession_number, item.primary_document): item
        for item in result
        if item.form in _ANNUAL_FORMS
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.filing_date, item.accession_number)))


def _filings_from_arrays(cik: int, payload: object) -> tuple[_SecFiling, ...]:
    if not isinstance(payload, dict):
        return ()
    accessions = payload.get("accessionNumber", [])
    dates = payload.get("filingDate", [])
    forms = payload.get("form", [])
    documents = payload.get("primaryDocument", [])
    if not all(isinstance(value, list) for value in (accessions, dates, forms, documents)):
        raise AutoIdentityImportError("SEC filing arrays are malformed")
    result: list[_SecFiling] = []
    for accession, filing_date_raw, form, document in zip(
        accessions, dates, forms, documents, strict=False
    ):
        try:
            filing_date = date.fromisoformat(str(filing_date_raw))
        except ValueError:
            continue
        accession_text = str(accession).strip()
        form_text = str(form).strip()
        document_text = str(document).strip()
        if accession_text and form_text and document_text:
            result.append(
                _SecFiling(
                    cik=cik,
                    form=form_text,
                    filing_date=filing_date,
                    accession_number=accession_text,
                    primary_document=document_text,
                )
            )
    return tuple(result)


def _find_exact_start(
    *,
    client: SecIdentityClient,
    company: _SecCompany,
    filings: tuple[_SecFiling, ...],
    observed_first_date: date,
) -> AutoIdentityEvidence | None:
    years = {
        observed_first_date.year - 1,
        observed_first_date.year,
        observed_first_date.year + 1,
        observed_first_date.year + 2,
    }
    for filing in filings:
        if filing.filing_date.year not in years:
            continue
        try:
            text = _normalize(client.get_text(filing.source_url))
        except AutoIdentityImportError:
            continue
        if _contains_exact_start(text, company.ticker, observed_first_date):
            return AutoIdentityEvidence(
                source_symbol=company.ticker,
                observed_first_date=observed_first_date,
                cik=company.cik,
                company_name=company.name,
                exchange=company.exchange,
                source_url=filing.source_url,
                source_title=f"SEC {filing.form} filed {filing.filing_date.isoformat()}",
                evidence_kind="EXACT_PUBLIC_TRADING_START",
                ready=True,
                reason="SEC filing independently confirms the exact provider-history start",
            )
    return None


def _find_campaign_continuity(
    *,
    client: SecIdentityClient,
    company: _SecCompany,
    filings: tuple[_SecFiling, ...],
    campaign_start: date,
) -> AutoIdentityEvidence | None:
    terms = _EXCHANGE_TERMS.get(company.exchange)
    if terms is None:
        return None
    for filing in filings:
        if filing.filing_date.year not in {campaign_start.year, campaign_start.year + 1}:
            continue
        try:
            text = _normalize(client.get_text(filing.source_url))
        except AutoIdentityImportError:
            continue
        if _ticker_exchange_cooccur(text, company.ticker, terms):
            return AutoIdentityEvidence(
                source_symbol=company.ticker,
                observed_first_date=campaign_start,
                cik=company.cik,
                company_name=company.name,
                exchange=company.exchange,
                source_url=filing.source_url,
                source_title=f"SEC {filing.form} filed {filing.filing_date.isoformat()}",
                evidence_kind="CAMPAIGN_CONTINUITY",
                ready=True,
                reason=(
                    "provider history begins at the bounded campaign start and a near-start SEC "
                    "annual filing confirms the same ticker, registrant, and supported exchange"
                ),
            )
    return None


def _contains_exact_start(text: str, ticker: str, target: date) -> bool:
    ticker_pattern = re.compile(rf"(?<![a-z0-9]){re.escape(ticker.lower())}(?![a-z0-9])")
    for token in _date_tokens(target):
        start = 0
        while True:
            index = text.find(token, start)
            if index < 0:
                break
            snippet = text[max(0, index - 1400) : index + 1400]
            if ticker_pattern.search(snippet) and any(term in snippet for term in _TRADING_TERMS):
                return True
            start = index + len(token)
    return False


def _ticker_exchange_cooccur(text: str, ticker: str, terms: tuple[str, ...]) -> bool:
    ticker_pattern = re.compile(rf"(?<![a-z0-9]){re.escape(ticker.lower())}(?![a-z0-9])")
    for match in ticker_pattern.finditer(text):
        snippet = text[max(0, match.start() - 1200) : match.end() + 1200]
        if any(term in snippet for term in terms):
            return True
    return False


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", unescape(value)).upper().split()).lower()


def _date_tokens(value: date) -> tuple[str, ...]:
    return (
        value.isoformat().lower(),
        f"{value.strftime('%B')} {value.day}, {value.year}".lower(),
        f"{value.strftime('%b')} {value.day}, {value.year}".lower(),
        f"{value.month}/{value.day}/{value.year}".lower(),
    )


__all__ = [
    "AutoIdentityEvidence",
    "AutoIdentityImportError",
    "SecIdentityClient",
    "build_auto_reviewed_candidate",
    "candidate_dataset_version",
    "collect_auto_identity_evidence",
    "load_sec_catalog",
]
