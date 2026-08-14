from datetime import date

import trade_scout.data.deferred_identity_resolution as resolution
from trade_scout.data.auto_identity_import import AutoIdentityEvidence, _SecCompany, _SecFiling


class _FakeClient:
    def get_text(self, _url: str) -> str:
        return (
            "The common stock is listed on the New York Stock Exchange "
            "under the trading symbol ABC."
        )


def _deferred(
    symbol: str = "ABC",
    observed_first_date: date = date(2005, 6, 15),
) -> AutoIdentityEvidence:
    return AutoIdentityEvidence(
        source_symbol=symbol,
        observed_first_date=observed_first_date,
        cik=1234,
        company_name="ABC CORP",
        exchange="NYSE",
        source_url=None,
        source_title=None,
        evidence_kind="BOUNDARY_NOT_PROVEN",
        ready=False,
        reason="first-pass boundary not proven",
    )


def _filing(filing_date: date, form: str = "10-Q") -> _SecFiling:
    return _SecFiling(
        cik=1234,
        form=form,
        filing_date=filing_date,
        accession_number=f"0000001234-{filing_date.year % 100:02d}-000001",
        primary_document=f"abc-{filing_date.isoformat()}.htm",
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
    filing = _filing(date(2005, 3, 1), form="10-K")
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
    filing = _filing(date(2006, 2, 20), form="10-K")
    monkeypatch.setattr(resolution, "_load_all_filings", lambda _client, _cik: (filing,))

    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={"ABC": company},
        evidence=_deferred(),
    )

    assert not result.ready
    assert result.resolution_kind == "POST_BOUNDARY_ONLY"


def test_campaign_boundary_accepts_pre_boundary_same_cik_filing(monkeypatch) -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    pre = _filing(date(1995, 11, 15), form="10-Q")
    post = _filing(date(1996, 3, 15), form="10-Q")
    monkeypatch.setattr(
        resolution,
        "_load_all_filing_forms",
        lambda _client, _cik: (pre, post),
    )

    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={"ABC": company},
        evidence=_deferred(observed_first_date=date(1996, 1, 2)),
    )

    assert result.ready
    assert result.resolution_kind == "CAMPAIGN_BOUNDARY_BRACKETED_SEC_CONTINUITY"
    assert result.evidence_url == pre.source_url


def test_campaign_boundary_post_only_remains_deferred(monkeypatch) -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    post = _filing(date(1996, 3, 15), form="10-Q")
    monkeypatch.setattr(
        resolution,
        "_load_all_filing_forms",
        lambda _client, _cik: (post,),
    )

    result = resolution.resolve_deferred_identity(
        client=_FakeClient(),  # type: ignore[arg-type]
        catalog={"ABC": company},
        evidence=_deferred(observed_first_date=date(1996, 1, 2)),
    )

    assert not result.ready
    assert result.resolution_kind == "CAMPAIGN_BOUNDARY_POST_ONLY"
