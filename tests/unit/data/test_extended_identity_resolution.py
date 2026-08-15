from datetime import date

from trade_scout.data.auto_identity_import import _SecCompany, _SecFiling
from trade_scout.data.extended_identity_resolution import (
    _find_exact_start_any_form,
    _find_ticker_exchange_filing,
)


class _Client:
    def __init__(self, text_by_url: dict[str, str]) -> None:
        self._text_by_url = text_by_url

    def get_text(self, url: str) -> str:
        return self._text_by_url[url]


def _filing(form: str, filing_date: date, document: str) -> _SecFiling:
    return _SecFiling(
        cik=1234,
        form=form,
        filing_date=filing_date,
        accession_number="0000001234-00-000001",
        primary_document=document,
    )


def test_exact_start_can_be_proved_by_registration_form() -> None:
    company = _SecCompany(cik=1234, name="EXAMPLE INC", ticker="XYZ", exchange="Nasdaq")
    filing = _filing("S-1", date(2001, 6, 1), "s1.htm")
    client = _Client(
        {
            filing.source_url: (
                "Our common stock, trading symbol XYZ, began trading on June 15, 2001."
            )
        }
    )
    found = _find_exact_start_any_form(
        client=client,  # type: ignore[arg-type]
        company=company,
        filings=(filing,),
        observed_first_date=date(2001, 6, 15),
    )
    assert found == filing


def test_pre_boundary_ticker_exchange_continuity_is_required() -> None:
    company = _SecCompany(cik=1234, name="EXAMPLE INC", ticker="XYZ", exchange="NYSE")
    good = _filing("10-K", date(1999, 3, 1), "good.htm")
    bad = _filing("10-Q", date(1999, 2, 1), "bad.htm")
    client = _Client(
        {
            good.source_url: "XYZ common stock is listed on the New York Stock Exchange.",
            bad.source_url: "XYZ quarterly report.",
        }
    )
    found = _find_ticker_exchange_filing(
        client=client,  # type: ignore[arg-type]
        company=company,
        filings=(bad, good),
        boundary=date(2000, 1, 1),
        before=True,
    )
    assert found == good
