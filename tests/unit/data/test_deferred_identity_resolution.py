from datetime import date

import trade_scout.data.deferred_identity_resolution as resolution
from trade_scout.data.auto_identity_import import AutoIdentityEvidence, _SecCompany, _SecFiling


class _FakeClient:
    def get_text(self, _url: str) -> str:
        return (
            "The common stock is listed on the New York Stock Exchange "
            "under the trading symbol ABC."
        )


def _deferred(symbol: str = "ABC") -> AutoIdentityEvidence:
    return AutoIdentityEvidence(
        source_symbol=symbol,
        observed_first_date=date(2005, 6, 15),
        cik=1234,
        company_name="ABC CORP",
        exchange="NYSE",
        source_url=None,
        source_title=None,
        evidence_kind="BOUNDARY_NOT_PROVEN",
        ready=False,
        reason="first-pass boundary not proven",
    )


def test_share_class_alias_resolves_dot_to_sec_hyphen() -> None:
    company = _SecCompany(cik=1, name="EXAMPLE", ticker="ABC-A", exchange="NYSE")
    catalog = {"ABC-A": company}

    assert resolution._catalog_company(catalog, "ABC.A") == company


def test_protected_legacy_case_never_calls_sec() -> None:
    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={},
        evidence=_deferred(),
        protected_symbols=frozenset({"ABC"}),
    )

    assert not result.ready
    assert result.resolution_kind == "LEGACY_LINEAGE_PROTECTED"


def test_pre_boundary_same_registrant_ticker_exchange_is_ready(monkeypatch) -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    filing = _SecFiling(
        cik=1234,
        form="10-K",
        filing_date=date(2005, 3, 1),
        accession_number="0000001234-05-000001",
        primary_document="abc10k.htm",
    )
    monkeypatch.setattr(resolution, "_load_all_filings", lambda _client, _cik: (filing,))

    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={"ABC": company},
        evidence=_deferred(),
    )

    assert result.ready
    assert result.resolution_kind == "ESTABLISHED_PRE_BOUNDARY_CONTINUITY"
    assert result.cik == 1234
    assert result.evidence_url == filing.source_url


def test_post_boundary_only_evidence_remains_deferred(monkeypatch) -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    filing = _SecFiling(
        cik=1234,
        form="10-K",
        filing_date=date(2006, 2, 20),
        accession_number="0000001234-06-000001",
        primary_document="abc10k.htm",
    )
    monkeypatch.setattr(resolution, "_load_all_filings", lambda _client, _cik: (filing,))

    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={"ABC": company},
        evidence=_deferred(),
    )

    assert not result.ready
    assert result.resolution_kind == "POST_BOUNDARY_ONLY"
