import json
from pathlib import Path

import pytest

from trade_scout.data.resolved_identity_batch import (
    ResolvedIdentityBatchError,
    load_resolved_identity_batch,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_combines_deferred_and_historical_ready_with_symbol_alias(tmp_path: Path) -> None:
    deferred_ready = tmp_path / "ready.json"
    remaining = tmp_path / "remaining.json"
    historical_ready = tmp_path / "historical.json"

    _write(
        deferred_ready,
        {
            "resolutions": [
                {
                    "source_symbol": "ABC",
                    "observed_first_date": "2005-06-15",
                    "status": "READY",
                    "resolution_kind": "BRACKETED_PRE_BOUNDARY_CONTINUITY",
                    "cik": 1234,
                    "company_name": "ABC CORP",
                    "exchange": "NYSE",
                    "evidence_url": "https://www.sec.gov/abc",
                    "evidence_title": "SEC 10-K",
                    "reason": "proved",
                }
            ]
        },
    )
    _write(
        remaining,
        {
            "resolutions": [
                {
                    "source_symbol": "BF.B",
                    "observed_first_date": "1996-01-02",
                    "cik": 5678,
                    "company_name": "BROWN FORMAN CORP",
                    "exchange": "NYSE",
                }
            ]
        },
    )
    _write(
        historical_ready,
        {
            "evidence": [
                {
                    "symbol": "BF-B",
                    "cik": 5678,
                    "status": "READY",
                    "kind": "SEC_FULL_INDEX_BRACKETED_CONTINUITY",
                    "pre_boundary_url": "https://www.sec.gov/bfb-pre",
                    "post_boundary_url": "https://www.sec.gov/bfb-post",
                    "reason": "historically proved",
                }
            ]
        },
    )

    batch = load_resolved_identity_batch(
        deferred_ready_path=deferred_ready,
        deferred_remaining_path=remaining,
        historical_ready_path=historical_ready,
    )

    assert batch.deferred_resolver_count == 1
    assert batch.historical_index_count == 1
    assert [item.source_symbol for item in batch.evidence] == ["ABC", "BF.B"]
    assert batch.evidence[1].cik == 5678
    assert batch.evidence[1].source_url == "https://www.sec.gov/bfb-pre"


def test_rejects_duplicate_ready_symbol(tmp_path: Path) -> None:
    deferred_ready = tmp_path / "ready.json"
    remaining = tmp_path / "remaining.json"
    historical_ready = tmp_path / "historical.json"

    _write(
        deferred_ready,
        {
            "resolutions": [
                {
                    "source_symbol": "ABC",
                    "observed_first_date": "1996-01-02",
                    "status": "READY",
                    "resolution_kind": "READY_ONE",
                    "cik": 1234,
                    "company_name": "ABC CORP",
                    "exchange": "NYSE",
                    "evidence_url": "https://www.sec.gov/abc",
                    "evidence_title": None,
                    "reason": "proved",
                }
            ]
        },
    )
    _write(
        remaining,
        {
            "resolutions": [
                {
                    "source_symbol": "ABC",
                    "observed_first_date": "1996-01-02",
                    "cik": 1234,
                    "company_name": "ABC CORP",
                    "exchange": "NYSE",
                }
            ]
        },
    )
    _write(
        historical_ready,
        {
            "evidence": [
                {
                    "symbol": "ABC",
                    "cik": 1234,
                    "status": "READY",
                    "kind": "READY_TWO",
                    "pre_boundary_url": "https://www.sec.gov/abc-pre",
                    "post_boundary_url": None,
                    "reason": "also proved",
                }
            ]
        },
    )

    with pytest.raises(ResolvedIdentityBatchError, match="duplicate READY evidence"):
        load_resolved_identity_batch(
            deferred_ready_path=deferred_ready,
            deferred_remaining_path=remaining,
            historical_ready_path=historical_ready,
        )


def test_rejects_historical_cik_mismatch(tmp_path: Path) -> None:
    deferred_ready = tmp_path / "ready.json"
    remaining = tmp_path / "remaining.json"
    historical_ready = tmp_path / "historical.json"
    _write(deferred_ready, {"resolutions": []})
    _write(
        remaining,
        {
            "resolutions": [
                {
                    "source_symbol": "XYZ",
                    "observed_first_date": "1996-01-02",
                    "cik": 111,
                    "company_name": "XYZ INC",
                    "exchange": "NASDAQ",
                }
            ]
        },
    )
    _write(
        historical_ready,
        {
            "evidence": [
                {
                    "symbol": "XYZ",
                    "cik": 222,
                    "status": "READY",
                    "kind": "SEC_FULL_INDEX_PRE_BOUNDARY_CONTINUITY",
                    "pre_boundary_url": "https://www.sec.gov/xyz",
                    "post_boundary_url": None,
                    "reason": "proved",
                }
            ]
        },
    )

    with pytest.raises(ResolvedIdentityBatchError, match="CIK differs"):
        load_resolved_identity_batch(
            deferred_ready_path=deferred_ready,
            deferred_remaining_path=remaining,
            historical_ready_path=historical_ready,
        )
