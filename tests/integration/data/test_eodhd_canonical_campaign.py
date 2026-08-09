from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd import EodhdBytesTransport
from trade_scout.data.providers.eodhd_campaign import (
    EodhdCampaignCase,
    EodhdCampaignError,
    run_eodhd_canonical_case,
)


class FixtureTransport(EodhdBytesTransport):
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str, *, timeout: float) -> bytes:
        assert timeout > 0
        self.urls.append(url)
        if not self._responses:
            raise AssertionError(f"unexpected EODHD request: {url}")
        return json.dumps(self._responses.pop(0)).encode()


def _active_inventory(*, isin: str | None = "US0378331005") -> list[dict[str, object]]:
    return [
        {
            "Code": "AAPL",
            "Name": "Apple Inc",
            "Exchange": "NASDAQ",
            "Currency": "USD",
            "Type": "Common Stock",
            "Isin": isin,
        }
    ]


def _responses(*, isin: str | None = "US0378331005") -> list[object]:
    return [
        _active_inventory(isin=isin),
        [],
        [
            {
                "date": "2020-08-28",
                "open": 400.0,
                "high": 400.0,
                "low": 400.0,
                "close": 400.0,
                "volume": 1000.0,
            },
            {
                "date": "2020-08-31",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 4000.0,
            },
        ],
        [{"date": "2020-08-31", "split": "4.000000/1.000000"}],
        [],
    ]


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, responses: list[object]):
    transport = FixtureTransport(responses)

    from trade_scout.data.providers import eodhd_campaign
    from trade_scout.data.providers.eodhd import EodhdHttpClient

    original_init = EodhdHttpClient.__init__

    def patched_init(self, api_token, *, transport=None, raw_capture=None, timeout=30.0):
        original_init(
            self,
            api_token,
            transport=transport_fixture,
            raw_capture=raw_capture,
            timeout=timeout,
        )

    transport_fixture = transport
    monkeypatch.setattr(eodhd_campaign.EodhdHttpClient, "__init__", patched_init)

    result = run_eodhd_canonical_case(
        "test-token",
        EodhdCampaignCase(
            symbol="AAPL.US",
            start=date(2020, 8, 28),
            end=date(2020, 8, 31),
            expected_active=True,
        ),
        raw_root=tmp_path / "raw",
        canonical_store=CanonicalDailyBarStore(tmp_path / "canonical"),
        dataset_id="eodhd-evaluation",
        dataset_version=DatasetVersion("eodhd-evaluation-v1"),
        created_at=datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
        transformation_version="normalization-v1",
        adjustment_policy_version="split-only-v1",
        universe_construction_version="evaluation-scope-v1",
        quality_check_version="quality-v1",
    )
    return result, transport


def test_campaign_promotes_split_adjusted_canonical_sample_with_raw_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, transport = _run(tmp_path, monkeypatch, _responses())

    assert result.symbol == "AAPL.US"
    assert result.provider_instrument_id == "eodhd:isin:US0378331005"
    assert result.bar_count == 2
    assert result.split_count == 1
    assert result.dividend_count == 0
    assert len(result.raw_batch_ids) == 5
    assert result.manifest.source_batch_ids == result.raw_batch_ids
    assert result.manifest.record_count == 2
    assert len(transport.urls) == 5

    stored = CanonicalDailyBarStore(tmp_path / "canonical").load(
        DatasetVersion("eodhd-evaluation-v1")
    )
    assert stored[0].close_raw == 400.0
    assert stored[0].close_split_adjusted == 100.0
    assert stored[1].close_raw == 100.0
    assert stored[1].close_split_adjusted == 100.0


def test_campaign_refuses_provisional_symbol_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EodhdCampaignError, match="durable ISIN identity"):
        _run(tmp_path, monkeypatch, _responses(isin=None))
