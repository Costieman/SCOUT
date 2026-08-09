"""Serialize a prepared EODHD daily-update assessment into runtime evidence."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.providers.eodhd_daily_update import assess_eodhd_daily_update
from trade_scout.data.providers.eodhd_daily_update_report import write_eodhd_daily_update_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assess two prepared EODHD canonical-bar slices and emit a strict incremental-update "
            "runtime report. This does not perform provider calls."
        )
    )
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--correction-window-start", type=date.fromisoformat, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--live-provider-observation", action="store_true")
    return parser


def _load(path: Path) -> tuple[DailyBar, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"daily-bar input must be a JSON list: {path}")
    bars: list[DailyBar] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise SystemExit(f"daily-bar entries must be JSON objects: {path}")
        bars.append(
            DailyBar(
                instrument_id=InstrumentId(str(raw["instrument_id"])),
                trade_date=date.fromisoformat(str(raw["trade_date"])),
                open_raw=float(raw["open_raw"]),
                high_raw=float(raw["high_raw"]),
                low_raw=float(raw["low_raw"]),
                close_raw=float(raw["close_raw"]),
                volume_raw=float(raw["volume_raw"]),
                split_factor=float(raw["split_factor"]),
                dividend_cash=float(raw["dividend_cash"]),
                open_split_adjusted=_optional_float(raw.get("open_split_adjusted")),
                high_split_adjusted=_optional_float(raw.get("high_split_adjusted")),
                low_split_adjusted=_optional_float(raw.get("low_split_adjusted")),
                close_split_adjusted=_optional_float(raw.get("close_split_adjusted")),
                provider_id=str(raw["provider_id"]),
                dataset_version=DatasetVersion(str(raw["dataset_version"])),
                quality_status=QualityStatus(str(raw["quality_status"])),
            )
        )
    return tuple(bars)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def main() -> int:
    args = _parser().parse_args()
    evidence = assess_eodhd_daily_update(
        _load(args.base),
        _load(args.incoming),
        target_dataset_version=DatasetVersion(args.target_version),
        correction_window_start=args.correction_window_start,
    )
    report = write_eodhd_daily_update_report(
        evidence,
        path=args.report,
        live_provider_observation=args.live_provider_observation,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
