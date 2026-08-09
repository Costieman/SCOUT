from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.alpha_vantage_characterization import (
    AlphaVantageResponseClass,
    characterize_raw_root,
    summarize_characterization,
)


def _batch(root: Path, name: str, payload: bytes, *, params: dict[str, object]) -> None:
    batch = root / name
    batch.mkdir(parents=True)
    (batch / "payload.bin").write_bytes(payload)
    (batch / "manifest.json").write_text(
        json.dumps(
            {
                "batch_id": name,
                "retrieval_time": f"2026-08-09T00:00:0{name[-1]}+00:00",
                "request_parameters": params,
                "media_type": "application/json" if payload.lstrip().startswith(b"{") else "text/csv",
            }
        ),
        encoding="utf-8",
    )


def test_characterizes_csv_empty_json_and_api_message(tmp_path: Path) -> None:
    _batch(tmp_path, "batch-1", b"symbol,name\nA,Alpha\n", params={"function": "LISTING_STATUS"})
    _batch(
        tmp_path,
        "batch-2",
        b"{}",
        params={"function": "LISTING_STATUS", "date": "2021-10-01", "state": "active"},
    )
    _batch(
        tmp_path,
        "batch-3",
        b'{"Note":"request frequency exceeded"}',
        params={"function": "TIME_SERIES_DAILY", "symbol": "AAPL"},
    )

    responses = characterize_raw_root(tmp_path)

    assert [item.response_class for item in responses] == [
        AlphaVantageResponseClass.CSV,
        AlphaVantageResponseClass.EMPTY_JSON,
        AlphaVantageResponseClass.API_MESSAGE_JSON,
    ]
    assert responses[1].request_parameters["date"] == "2021-10-01"
    assert responses[2].message_key == "Note"


def test_summary_does_not_infer_cause_for_empty_json(tmp_path: Path) -> None:
    _batch(tmp_path, "batch-1", b"{}", params={"function": "LISTING_STATUS"})

    summary = summarize_characterization(characterize_raw_root(tmp_path))

    assert summary["class_counts"]["EMPTY_JSON"] == 1
    assert "must not be relabelled" in summary["interpretation"]
