from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.run_eodhd_campaign_benchmark import _load_instruments


def test_load_instruments_accepts_aggregate_report(tmp_path: Path) -> None:
    path = tmp_path / "aggregate.json"
    path.write_text(
        json.dumps(
            {
                "instruments": [
                    {
                        "instrument_id": "isin:US0000000001",
                        "symbol": "AAA",
                        "name": "AAA Corp",
                        "exchange": "NYSE",
                        "security_type": "common_stock",
                        "currency": "USD",
                        "first_trade_date": "2010-01-01",
                        "delisting_date": None,
                        "provider_instrument_id": "US0000000001",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    instruments = _load_instruments(path)
    assert len(instruments) == 1
    assert instruments[0].primary_symbol == "AAA"


def test_load_instruments_rejects_missing_instrument_list(tmp_path: Path) -> None:
    path = tmp_path / "aggregate.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="instruments"):
        _load_instruments(path)
