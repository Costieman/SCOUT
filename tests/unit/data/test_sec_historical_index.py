from datetime import date

from trade_scout.data.auto_identity_import import _SecCompany
from trade_scout.data.sec_historical_index import (
    HistoricalIndexFiling,
    _parse_master_index,
    resolve_historical_campaign_boundary,
)


class _FakeClient:
    def __init__(self, text_by_url: dict[str, str]) -> None:
        self._text_by_url = text_by_url

    def get_text(self, url: str) -> str:
        return self._text_by_url[url]


def test_parse_master_index_filters_requested_dates() -> None:
    text = "\n".join(
        [
            "CIK|Company Name|Form Type|Date Filed|Filename",
            "1234|ABC CORP|10-Q|1995-11-01|edgar/data/1234/a.txt",
            "5678|XYZ CORP|8-K|1997-01-01|edgar/data/5678/b.txt",
        ]
    )
    rows = _parse_master_index(text, start=date(1995, 1, 1), end=date(1996, 3, 31))
    assert len(rows) == 1
    assert rows[0].cik == 1234


def test_historical_boundary_bracketed_same_cik_ticker_exchange() -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    pre = HistoricalIndexFiling(1234, "ABC CORP", "10-Q", date(1995, 11, 1), "edgar/data/1234/pre.txt")
    post = HistoricalIndexFiling(1234, "ABC CORP", "10-K", date(1996, 2, 20), "edgar/data/1234/post.txt")
    body = "The common stock is listed on the New York Stock Exchange under the symbol ABC."
    client = _FakeClient({pre.source_url: body, post.source_url: body})

    result = resolve_historical_campaign_boundary(
        client=client,  # type: ignore[arg-type]
        company=company,
        boundary=date(1996, 1, 2),
        index_rows=(pre, post),
    )

    assert result.ready
    assert result.kind == "SEC_FULL_INDEX_BRACKETED_CONTINUITY"
    assert result.pre_boundary_url == pre.source_url


def test_wrong_cik_cannot_prove_boundary() -> None:
    company = _SecCompany(cik=1234, name="ABC CORP", ticker="ABC", exchange="NYSE")
    other = HistoricalIndexFiling(9999, "ABC OLD", "10-Q", date(1995, 11, 1), "edgar/data/9999/pre.txt")
    client = _FakeClient({})

    result = resolve_historical_campaign_boundary(
        client=client,  # type: ignore[arg-type]
        company=company,
        boundary=date(1996, 1, 2),
        index_rows=(other,),
    )

    assert not result.ready
    assert result.kind == "NO_PRE_BOUNDARY_INDEX_FILING"
