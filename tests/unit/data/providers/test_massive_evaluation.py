from datetime import date

import pytest

from trade_scout.data.providers.massive import MassiveIdentityError
from trade_scout.data.providers.massive_evaluation import discover_massive_evaluation_instrument


class FakeClient:
    def __init__(self, *, ambiguous: bool = False) -> None:
        self.ambiguous = ambiguous

    def get_json(self, endpoint: str, parameters=None):  # type: ignore[no-untyped-def]
        assert endpoint == "/v3/reference/tickers"
        active = parameters["active"]
        if active is False and not self.ambiguous:
            return {"results": []}
        figi = "FIGI-2" if active is False else "FIGI-1"
        return {
            "results": [
                {
                    "ticker": "AAA",
                    "name": "Example Corp",
                    "primary_exchange": "XNYS",
                    "currency_name": "usd",
                    "active": active,
                    "composite_figi": figi,
                    "list_date": "2020-01-02",
                    "delisted_utc": None,
                }
            ]
        }


def test_discovery_returns_one_figi_backed_reference_record() -> None:
    instrument = discover_massive_evaluation_instrument(
        FakeClient(),  # type: ignore[arg-type]
        symbol="AAA",
        as_of=date(2026, 6, 18),
    )

    assert instrument.provider_instrument_id == "FIGI-1"
    assert instrument.symbol == "AAA"
    assert instrument.active is True
    assert instrument.first_trade_date == date(2020, 1, 2)


def test_discovery_rejects_ambiguous_stable_identity() -> None:
    with pytest.raises(MassiveIdentityError, match="found 2"):
        discover_massive_evaluation_instrument(
            FakeClient(ambiguous=True),  # type: ignore[arg-type]
            symbol="AAA",
            as_of=date(2026, 6, 18),
        )
