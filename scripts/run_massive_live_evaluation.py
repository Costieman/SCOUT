"""Run the small real-data evaluation against the Massive candidate adapter."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from trade_scout.data.contracts import CorporateActionType, DatasetVersion
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    ProviderAdapter,
    ProviderCorporateAction,
    ProviderDailyBar,
    ProviderHealth,
    ProviderInstrument,
    ProviderSymbolHistory,
)
from trade_scout.data.provider_evaluation import (
    ProviderEvaluationCase,
    ProviderEvaluationReport,
    evaluate_provider_adapter,
)
from trade_scout.data.providers.massive import MassiveAdapter, MassiveHttpClient, RawStoreCapture
from trade_scout.data.providers.massive_evaluation import discover_massive_evaluation_instrument
from trade_scout.data.providers.massive_transport import RetryingUrllibBytesTransport
from trade_scout.data.raw_store import RawBatchStore

_DATASET_VERSION = DatasetVersion("massive-live-evaluation-2026-08-08-v2")


@dataclass(frozen=True, slots=True)
class SampleSpec:
    case_id: str
    symbol: str
    discovery_date: date
    start: date
    end: date
    expected_active: bool | None = None
    required_action_types: frozenset[CorporateActionType] = frozenset()
    require_symbol_history: bool = False


@dataclass(frozen=True, slots=True)
class CaseRun:
    case_id: str
    symbol: str
    provider_instrument_id: str | None
    report: dict[str, Any] | None
    error: str | None


class SampleAdapterView:
    """ProviderAdapter view that limits instrument discovery to one pre-resolved sample record."""

    def __init__(self, delegate: MassiveAdapter, instrument: ProviderInstrument) -> None:
        self._delegate = delegate
        self._instrument = instrument
        self.provider_id = delegate.provider_id

    def describe_capabilities(self):  # type: ignore[no-untyped-def]
        return self._delegate.describe_capabilities()

    def health_check(self) -> ProviderHealth:
        return self._delegate.health_check()

    def get_instruments(self, *, as_of: date | None = None) -> tuple[ProviderInstrument, ...]:
        del as_of
        return (self._instrument,)

    def get_symbol_history(
        self, *, provider_instrument_ids: tuple[str, ...] | None = None
    ) -> tuple[ProviderSymbolHistory, ...]:
        return tuple(
            self._delegate.get_symbol_history(provider_instrument_ids=provider_instrument_ids)
        )

    def get_daily_bars(self, request: DailyBarRequest) -> tuple[ProviderDailyBar, ...]:
        return tuple(self._delegate.get_daily_bars(request))

    def get_corporate_actions(
        self, request: CorporateActionRequest
    ) -> tuple[ProviderCorporateAction, ...]:
        return tuple(self._delegate.get_corporate_actions(request))


def main() -> int:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is not configured")

    output_root = Path(os.environ.get("TRADE_SCOUT_EVALUATION_ROOT", "runtime/massive-evaluation"))
    report_root = output_root / "report"
    raw_root = output_root / "raw"
    report_root.mkdir(parents=True, exist_ok=True)

    raw_store = RawBatchStore(raw_root)
    interval_seconds = float(os.environ.get("MASSIVE_EVAL_MIN_REQUEST_INTERVAL_SECONDS", "12.5"))
    transport = RetryingUrllibBytesTransport(min_interval_seconds=interval_seconds)
    client = MassiveHttpClient(
        api_key,
        transport=transport,
        raw_capture=RawStoreCapture(raw_store),
    )
    adapter = MassiveAdapter(client)

    case_runs = tuple(_run_case(adapter, client, spec) for spec in _sample_specs())
    raw_evidence = _raw_evidence(raw_root)
    payload = {
        "evaluation_id": str(_DATASET_VERSION),
        "provider_id": adapter.provider_id,
        "generated_for": "Trade Scout Phase 1 provider acceptance gate",
        "request_interval_seconds": interval_seconds,
        "case_runs": [asdict(item) for item in case_runs],
        "raw_capture": {
            "manifest_count": len(raw_evidence),
            "evidence": raw_evidence,
            "payload_bytes_uploaded": False,
        },
        "provider_accepted": False,
        "acceptance_note": (
            "Automated live evidence does not by itself accept Massive. Licensing/storage rights, "
            "correction behavior, and representative historical benchmarking remain explicit gates."
        ),
    }
    json_path = report_root / "massive-live-evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "massive-live-evaluation.md"
    markdown_path.write_text(_markdown_report(payload), encoding="utf-8")

    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _run_case(
    adapter: MassiveAdapter,
    client: MassiveHttpClient,
    spec: SampleSpec,
) -> CaseRun:
    provider_instrument_id: str | None = None
    try:
        instrument = discover_massive_evaluation_instrument(
            client,
            symbol=spec.symbol,
            as_of=spec.discovery_date,
        )
        provider_instrument_id = instrument.provider_instrument_id
        case = ProviderEvaluationCase(
            case_id=spec.case_id,
            provider_instrument_id=instrument.provider_instrument_id,
            provider_symbol=spec.symbol,
            start=spec.start,
            end=spec.end,
            expected_active=spec.expected_active,
            required_action_types=spec.required_action_types,
            require_symbol_history=spec.require_symbol_history,
        )
        view: ProviderAdapter = SampleAdapterView(adapter, instrument)
        report = evaluate_provider_adapter(view, (case,), dataset_version=_DATASET_VERSION)
        return CaseRun(
            case_id=spec.case_id,
            symbol=spec.symbol,
            provider_instrument_id=provider_instrument_id,
            report=_evaluation_report_dict(report),
            error=None,
        )
    except Exception as exc:
        return CaseRun(
            case_id=spec.case_id,
            symbol=spec.symbol,
            provider_instrument_id=provider_instrument_id,
            report=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def _sample_specs() -> tuple[SampleSpec, ...]:
    return (
        SampleSpec(
            case_id="active_recent_aapl",
            symbol="AAPL",
            discovery_date=date(2026, 6, 18),
            start=date(2026, 6, 15),
            end=date(2026, 6, 18),
            expected_active=True,
        ),
        SampleSpec(
            case_id="cash_dividend_aapl_2026_05",
            symbol="AAPL",
            discovery_date=date(2026, 5, 11),
            start=date(2026, 5, 7),
            end=date(2026, 5, 12),
            expected_active=True,
            required_action_types=frozenset({CorporateActionType.CASH_DIVIDEND}),
        ),
        SampleSpec(
            case_id="split_ctas_2024_09",
            symbol="CTAS",
            discovery_date=date(2024, 9, 12),
            start=date(2024, 9, 10),
            end=date(2024, 9, 13),
            expected_active=True,
            required_action_types=frozenset({CorporateActionType.SPLIT}),
        ),
        SampleSpec(
            case_id="delisted_para_2025_08",
            symbol="PARA",
            discovery_date=date(2025, 8, 8),
            start=date(2025, 8, 1),
            end=date(2025, 8, 6),
            expected_active=False,
        ),
        SampleSpec(
            case_id="symbol_history_xyz",
            symbol="XYZ",
            discovery_date=date(2026, 6, 18),
            start=date(2026, 6, 15),
            end=date(2026, 6, 18),
            expected_active=True,
            require_symbol_history=True,
        ),
    )


def _evaluation_report_dict(report: ProviderEvaluationReport) -> dict[str, Any]:
    return {
        "provider_id": report.provider_id,
        "health": {
            "status": str(report.health.status),
            "message": report.health.message,
        },
        "automated_gate_passed": report.automated_gate_passed,
        "provider_accepted": report.provider_accepted,
        "top_level_checks": [
            {"check_id": check.check_id, "state": str(check.state), "detail": check.detail}
            for check in report.checks
        ],
        "cases": [
            {
                "case_id": case.case_id,
                "daily_bar_count": case.daily_bar_count,
                "corporate_action_count": case.corporate_action_count,
                "normalization_status": (
                    str(case.normalization_status)
                    if case.normalization_status is not None
                    else None
                ),
                "automated_gate_passed": case.automated_gate_passed,
                "checks": [
                    {"check_id": check.check_id, "state": str(check.state), "detail": check.detail}
                    for check in case.checks
                ],
            }
            for case in report.cases
        ],
        "unresolved_manual_gates": list(report.unresolved_manual_gates),
    }


def _raw_evidence(raw_root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for path in sorted(raw_root.rglob("manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        evidence.append(
            {
                "batch_id": manifest["batch_id"],
                "provider_id": manifest["provider_id"],
                "endpoint": manifest["endpoint"],
                "retrieval_time": manifest["retrieval_time"],
                "checksum_sha256": manifest["checksum_sha256"],
                "content_length": manifest["content_length"],
            }
        )
    return evidence


def _markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Massive live provider evaluation",
        "",
        f"Evaluation: `{payload['evaluation_id']}`",
        f"Request interval: **{payload['request_interval_seconds']} seconds**",
        "",
        "**Provider acceptance: NO.** This run collects evidence; it does not close manual gates.",
        "",
        "## Cases",
        "",
    ]
    for case in payload["case_runs"]:
        lines.append(f"### {case['case_id']} ({case['symbol']})")
        lines.append("")
        if case["error"] is not None:
            lines.append(f"- Execution error: `{case['error']}`")
            lines.append("")
            continue
        report = case["report"]
        lines.append(f"- Stable provider ID: `{case['provider_instrument_id']}`")
        lines.append(f"- Automated gate passed: **{report['automated_gate_passed']}**")
        for evaluated in report["cases"]:
            lines.append(f"- Daily bars: {evaluated['daily_bar_count']}")
            lines.append(f"- Corporate actions: {evaluated['corporate_action_count']}")
            lines.append(f"- Normalization: `{evaluated['normalization_status']}`")
            for check in evaluated["checks"]:
                lines.append(f"  - `{check['state']}` {check['check_id']}: {check['detail']}")
        lines.append("")

    raw = payload["raw_capture"]
    lines.extend(
        [
            "## Raw-response evidence",
            "",
            f"- Captured response manifests: **{raw['manifest_count']}**",
            "- Raw payload bytes are deliberately not uploaded as workflow artifacts.",
            "- The JSON report records endpoint, retrieval time, byte length, and SHA-256 only.",
            "",
            "## Remaining manual gates",
            "",
            "- Confirm Massive licensing/storage rights for the intended Trade Scout use.",
            "- Characterize corrections by repeating the same logical retrieval at a later time.",
            "- Run the representative multi-year Parquet/DuckDB benchmark after provider "
            "acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
