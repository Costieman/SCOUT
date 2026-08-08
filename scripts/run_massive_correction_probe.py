"""Capture a bounded Massive daily-bar snapshot for later revision comparison."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from trade_scout.data.correction_probe import capture_daily_bar_correction_snapshot
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.massive import MassiveAdapter, MassiveHttpClient, RawStoreCapture
from trade_scout.data.providers.massive_transport import RetryingUrllibBytesTransport
from trade_scout.data.raw_store import RawBatchStore


def main() -> int:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is not configured")

    output_root = Path(os.environ.get("TRADE_SCOUT_CORRECTION_ROOT", "runtime/correction-probe"))
    report_root = output_root / "report"
    raw_root = output_root / "raw"
    report_root.mkdir(parents=True, exist_ok=True)

    interval_seconds = float(os.environ.get("MASSIVE_EVAL_MIN_REQUEST_INTERVAL_SECONDS", "12.5"))
    client = MassiveHttpClient(
        api_key,
        transport=RetryingUrllibBytesTransport(min_interval_seconds=interval_seconds),
        raw_capture=RawStoreCapture(RawBatchStore(raw_root)),
    )
    adapter = MassiveAdapter(client)
    request = DailyBarRequest(
        start=date(2026, 6, 15),
        end=date(2026, 6, 18),
        provider_symbols=("AAPL",),
        run_id="massive-correction-probe:aapl-2026-06-15-18",
    )
    snapshot = capture_daily_bar_correction_snapshot(adapter, request)
    report = {
        "captured_at": datetime.now(UTC).isoformat(),
        "request_interval_seconds": interval_seconds,
        "request": {
            "provider_id": adapter.provider_id,
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "provider_symbols": list(request.provider_symbols or ()),
        },
        "snapshot": asdict(snapshot),
        "raw_evidence": _raw_evidence(raw_root),
        "interpretation": (
            "This is a baseline or follow-up snapshot only. Provider correction behavior is "
            "characterized by comparing an identical logical request captured at a later time."
        ),
    }

    json_path = report_root / "massive-correction-probe.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "massive-correction-probe.md"
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _raw_evidence(raw_root: Path) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for path in sorted(raw_root.rglob("manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        evidence.append(
            {
                "endpoint": manifest["endpoint"],
                "request_parameters": manifest["request_parameters"],
                "retrieval_time": manifest["retrieval_time"],
                "checksum_sha256": manifest["checksum_sha256"],
                "content_length": manifest["content_length"],
            }
        )
    return evidence


def _markdown(report: dict[str, object]) -> str:
    snapshot = report["snapshot"]
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot report entry must be an object")
    return "\n".join(
        [
            "# Massive correction probe",
            "",
            f"Captured: `{report['captured_at']}`",
            "",
            "This report is not provider acceptance. It records one logical response for a later "
            "same-request comparison.",
            "",
            f"- Provider: `{snapshot['provider_id']}`",
            f"- Window: `{snapshot['start']}` to `{snapshot['end']}`",
            f"- Symbols: `{', '.join(snapshot['provider_symbols'])}`",
            f"- Records: **{snapshot['record_count']}**",
            f"- Logical SHA-256: `{snapshot['logical_sha256']}`",
            f"- Raw response manifests: **{len(report['raw_evidence'])}**",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
