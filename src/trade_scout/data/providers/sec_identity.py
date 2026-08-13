"""Primary-source SEC evidence collection for automated equity identity triage.

The collector is intentionally conservative. It can establish only two facts automatically:
(1) an exact public-trading/listing start equal to the durable provider start, or
(2) bounded campaign-start continuity for a same registrant/ticker on a supported exchange.
Everything else remains unresolved for explicit review.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from html import unescape

from trade_scout.data.identity_adjudication import IdentityEvidence, IdentityEvidenceState

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{name}"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_ANNUAL_FORMS = frozenset({"10-K", "10-K405", "10-KSB", "20-F", "40-F"})
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


class SecIdentityEvidenceError(RuntimeError):
    """Raised when SEC evidence cannot be fetched or parsed safely."""


@dataclass(frozen=True, slots=True)
class SecCompany:
    cik: int
    name: str
    ticker: str
    exchange: str


@dataclass(frozen=True, slots=True)
class SecFiling:
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


class SecHttpClient:
    """Small SEC HTTP client with declared identity, bounded retries, and rate pacing."""

    def __init__(
        self,
        *,
        user_agent: str,
        minimum_interval_seconds: float = 0.25,
        timeout_seconds: float = 45.0,
        max_attempts: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError(
                "SEC user_agent must identify the requester and include a contact email"
            )
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._headers = {
            "User-Agent": user_agent.strip(),
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }
        self._minimum_interval_seconds = minimum_interval_seconds
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._last_request_monotonic: float | None = None

    def get_json(self, url: str) -> object:
        return json.loads(self.get_text(url))

    def get_text(self, url: str) -> str:
        for attempt in range(1, self._max_attempts + 1):
            self._pace()
            request = urllib.request.Request(url, headers=self._headers)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                    return response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == self._max_attempts:
                    raise SecIdentityEvidenceError(
                        f"SEC request failed with HTTP {exc.code}: {url}"
                    ) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else 2.0**attempt
                )
                self._sleep(delay)
            except OSError as exc:
                if attempt == self._max_attempts:
                    raise SecIdentityEvidenceError(f"SEC request failed: {url}") from exc
                self._sleep(2.0**attempt)
        raise AssertionError("unreachable SEC retry state")

    def _pace(self) -> None:
        now = time.monotonic()
        if self._last_request_monotonic is not None:
            elapsed = now - self._last_request_monotonic
            remaining = self._minimum_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_monotonic = time.monotonic()


def load_sec_company_catalog(client: SecHttpClient) -> Mapping[str, SecCompany]:
    """Load current SEC ticker/CIK/exchange associations keyed by uppercase ticker."""

    payload = client.get_json(_COMPANY_TICKERS_URL)
    if not isinstance(payload, dict):
        raise SecIdentityEvidenceError("SEC ticker catalog root must be an object")
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise SecIdentityEvidenceError("SEC ticker catalog has unsupported structure")
    expected = {"cik", "name", "ticker", "exchange"}
    if not expected.issubset({str(item) for item in fields}):
        raise SecIdentityEvidenceError("SEC ticker catalog is missing required fields")
    indexes = {str(value): index for index, value in enumerate(fields)}
    result: dict[str, SecCompany] = {}
    for raw in data:
        if not isinstance(raw, list):
            continue
        try:
            ticker = str(raw[indexes["ticker"]]).strip().upper()
            company = SecCompany(
                cik=int(raw[indexes["cik"]]),
                name=str(raw[indexes["name"]]).strip(),
                ticker=ticker,
                exchange=str(raw[indexes["exchange"]]).strip(),
            )
        except (IndexError, TypeError, ValueError) as exc:
            raise SecIdentityEvidenceError("SEC ticker catalog contains malformed row") from exc
        if ticker:
            result[ticker] = company
    return result


def collect_sec_identity_evidence(
    *,
    client: SecHttpClient,
    catalog: Mapping[str, SecCompany],
    source_symbol: str,
    observed_first_date: date,
    campaign_start: date,
) -> IdentityEvidence:
    """Collect conservative primary-source evidence for one current ticker."""

    symbol = source_symbol.strip().upper()
    company = catalog.get(symbol)
    if company is None:
        return IdentityEvidence(
            source_symbol=symbol,
            state=IdentityEvidenceState.NO_SUPPORT,
            source_url=None,
            source_title=None,
            effective_date=None,
            regulator_id=None,
            company_name=None,
            exchange=None,
            detail="current ticker is not present in the SEC ticker/CIK catalog",
        )

    try:
        filings = _load_all_filings(client, company.cik)
    except SecIdentityEvidenceError as exc:
        return IdentityEvidence(
            source_symbol=symbol,
            state=IdentityEvidenceState.SOURCE_ERROR,
            source_url=None,
            source_title=None,
            effective_date=None,
            regulator_id=f"CIK{company.cik:010d}",
            company_name=company.name,
            exchange=company.exchange,
            detail=str(exc),
        )

    exact = _find_exact_start_evidence(
        client=client,
        company=company,
        filings=filings,
        observed_first_date=observed_first_date,
    )
    if exact is not None:
        return exact

    if observed_first_date == campaign_start:
        continuity = _find_campaign_continuity_evidence(
            client=client,
            company=company,
            filings=filings,
            campaign_start=campaign_start,
        )
        if continuity is not None:
            return continuity

    return IdentityEvidence(
        source_symbol=symbol,
        state=IdentityEvidenceState.CURRENT_REGISTRANT_ONLY,
        source_url=None,
        source_title=None,
        effective_date=None,
        regulator_id=f"CIK{company.cik:010d}",
        company_name=company.name,
        exchange=company.exchange,
        detail=(
            "SEC confirms the current ticker-to-registrant association but the automated pass did "
            "not find primary-source text sufficient to establish the provider-history boundary"
        ),
    )


def _load_all_filings(client: SecHttpClient, cik: int) -> tuple[SecFiling, ...]:
    payload = client.get_json(_SUBMISSIONS_URL.format(cik=cik))
    if not isinstance(payload, dict):
        raise SecIdentityEvidenceError("SEC submissions root must be an object")
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        raise SecIdentityEvidenceError("SEC submissions are missing filings")
    result = list(_filings_from_parallel_arrays(cik, filings.get("recent")))
    old_files = filings.get("files", [])
    if not isinstance(old_files, list):
        raise SecIdentityEvidenceError("SEC historical submissions file list is malformed")
    for item in old_files:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SecIdentityEvidenceError("SEC historical submissions file entry is malformed")
        old_payload = client.get_json(_SUBMISSIONS_FILE_URL.format(name=item["name"]))
        result.extend(_filings_from_parallel_arrays(cik, old_payload))
    unique = {
        (item.accession_number, item.primary_document): item
        for item in result
        if item.form in _ANNUAL_FORMS
    }
    return tuple(
        sorted(unique.values(), key=lambda item: (item.filing_date, item.accession_number))
    )


def _filings_from_parallel_arrays(cik: int, payload: object) -> tuple[SecFiling, ...]:
    if not isinstance(payload, dict):
        return ()
    accessions = payload.get("accessionNumber", [])
    dates = payload.get("filingDate", [])
    forms = payload.get("form", [])
    documents = payload.get("primaryDocument", [])
    if not all(isinstance(value, list) for value in (accessions, dates, forms, documents)):
        raise SecIdentityEvidenceError("SEC filing arrays are malformed")
    count = min(len(accessions), len(dates), len(forms), len(documents))
    result: list[SecFiling] = []
    for index in range(count):
        accession = str(accessions[index]).strip()
        form = str(forms[index]).strip()
        document = str(documents[index]).strip()
        try:
            filing_date = date.fromisoformat(str(dates[index]))
        except ValueError:
            continue
        if accession and form and document:
            result.append(
                SecFiling(
                    cik=cik,
                    form=form,
                    filing_date=filing_date,
                    accession_number=accession,
                    primary_document=document,
                )
            )
    return tuple(result)


def _find_exact_start_evidence(
    *,
    client: SecHttpClient,
    company: SecCompany,
    filings: tuple[SecFiling, ...],
    observed_first_date: date,
) -> IdentityEvidence | None:
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
            text = _normalize_document(client.get_text(filing.source_url))
        except SecIdentityEvidenceError:
            continue
        if _contains_exact_trading_start(text, company.ticker, observed_first_date):
            return IdentityEvidence(
                source_symbol=company.ticker,
                state=IdentityEvidenceState.EXACT_PUBLIC_TRADING_START,
                source_url=filing.source_url,
                source_title=f"SEC {filing.form} filed {filing.filing_date.isoformat()}",
                effective_date=observed_first_date,
                regulator_id=f"CIK{company.cik:010d}",
                company_name=company.name,
                exchange=company.exchange,
                detail=(
                    "SEC filing text contains the exact observed start date, ticker, and explicit "
                    "trading/listing language"
                ),
            )
    return None


def _find_campaign_continuity_evidence(
    *,
    client: SecHttpClient,
    company: SecCompany,
    filings: tuple[SecFiling, ...],
    campaign_start: date,
) -> IdentityEvidence | None:
    terms = _EXCHANGE_TERMS.get(company.exchange)
    if terms is None:
        return None
    for filing in filings:
        if filing.filing_date.year not in {campaign_start.year, campaign_start.year + 1}:
            continue
        try:
            text = _normalize_document(client.get_text(filing.source_url))
        except SecIdentityEvidenceError:
            continue
        if _ticker_and_exchange_cooccur(text, company.ticker, terms):
            return IdentityEvidence(
                source_symbol=company.ticker,
                state=IdentityEvidenceState.CAMPAIGN_CONTINUITY,
                source_url=filing.source_url,
                source_title=f"SEC {filing.form} filed {filing.filing_date.isoformat()}",
                effective_date=campaign_start,
                regulator_id=f"CIK{company.cik:010d}",
                company_name=company.name,
                exchange=company.exchange,
                detail=(
                    "SEC annual filing near the bounded campaign start identifies the same current "
                    "ticker and supported listing exchange for the same registrant"
                ),
            )
    return None


def _contains_exact_trading_start(text: str, ticker: str, target: date) -> bool:
    date_tokens = _date_tokens(target)
    ticker_pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(ticker.lower())}(?![a-z0-9])"
    )
    for token in date_tokens:
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


def _ticker_and_exchange_cooccur(text: str, ticker: str, terms: tuple[str, ...]) -> bool:
    ticker_pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(ticker.lower())}(?![a-z0-9])"
    )
    for match in ticker_pattern.finditer(text):
        snippet = text[max(0, match.start() - 1200) : match.end() + 1200]
        if any(term in snippet for term in terms):
            return True
    return False


def _normalize_document(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", unescape(value))
    return " ".join(no_tags.upper().split()).lower()


def _date_tokens(value: date) -> tuple[str, ...]:
    month = value.strftime("%B")
    abbreviated = value.strftime("%b")
    return (
        value.isoformat().lower(),
        f"{month} {value.day}, {value.year}".lower(),
        f"{abbreviated} {value.day}, {value.year}".lower(),
        f"{value.month}/{value.day}/{value.year}".lower(),
    )


__all__ = [
    "SecCompany",
    "SecFiling",
    "SecHttpClient",
    "SecIdentityEvidenceError",
    "collect_sec_identity_evidence",
    "load_sec_company_catalog",
]
