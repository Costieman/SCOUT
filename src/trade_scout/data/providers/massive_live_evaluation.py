"""Run the agreed real Massive sample without exposing credentials or raw vendor bytes."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from trade_scout.data.contracts import CorporateActionType, DatasetVersion
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    ProviderAdapter,
    ProviderCapabilities,
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
from trade_scout.data.providers.massive import MassiveAdapter

_EVALUATION_VERSION = DatasetVersion("massive-live-evaluation-2026-08-08-v1")


@dataclass(frozen=True, slots=True)
class _SampleSpec:
    case_id: str
    symbol: str
    start: date
    end: date
    expected_active: bool | None = None
    required_action_types: frozenset[CorporateActionType] = frozenset()
    require_symbol_history: bool = False


_SAMPLE_SPECS = (
    _SampleSpec(
        case_id="current_active_msft",
        symbol="MSFT",
        start=date(2026, 7, 27),
        end=date(2026, 8, 7),
        expected_active=True,
    ),
    _SampleSpec(
        case_id="aapl_2020_split_dividend",
        symbol="AAPL",
        start=date(2020, 8, 3),
        end=date(2020, 9, 4),
        expected_active=True,
        required_action_types=frozenset(
            {CorporateActionType.SPLIT, CorporateActionType.CASH_DIVIDEND}
        ),
    ),
    _SampleSpec(
        case_id="twtr_pre_delisting",
        symbol="TWTR",
        start=date(2022, 10, 3),
        end=date(2022, 10, 27),
        expected_active=False,
    ),
    _SampleSpec(
        case_id="meta_ticker_history",
        symbol="META",
        start=date(2022, 6, 9),
        end=date(2022, 6, 17),
        expected_active=True,
        require_symbol_history=True,
    ),
    _SampleSpec(
        case_id="abnb_ipo_window",
        symbol="ABNB",
        start=date(2020, 12, 10),
        end=date(2020, 12, 18),
        expected_active=True,
    ),
)


class _CachedInstrumentAdapter:
    """Delegate to a real adapter while reusing one expensive instrument inventory retrieval."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        instruments: tuple[ProviderInstrument, ...],
    ) -> None:
        self.provider_id = adapter.provider_id
        self._adapter = adapter
        self._instruments = instruments

    def describe_capabilities(self) -> ProviderCapabilities:
        return self._adapter.describe_capabilities()

    def health_check(self) -> ProviderHealth:
        return self._adapter.health_check()

    def get_instruments(self, *, as_of: date | None = None) -> Sequence[ProviderInstrument]:
        if as_of is None:
            return self._instruments
        return self._adapter.get_instruments(as_of=as_of)

    def get_symbol_history(
        self,
        *,
        provider_instrument_ids: Sequence[str] | None = None,
    ) -> Sequence[ProviderSymbolHistory]:
        return self._adapter.get_symbol_history(provider_instrument_ids=provider_instrument_ids)

    def get_daily_bars(self, request: DailyBarRequest) -> Sequence[ProviderDailyBar]:
        return self._adapter.get_daily_bars(request)

    def get_corporate_actions(
        self,
        request: CorporateActionRequest,
    ) -> Sequence[ProviderCorporateAction]:
        return self._adapter.get_corporate_actions(request)


def _report_to_dict(report: ProviderEvaluationReport) -> dict[str, Any]:
    return {
        "provider_id": report.provider_id,
        "automated_gate_passed": report.automated_gate_passed,
        "provider_accepted": report.provider_accepted,
        "health": {
            "status": str(report.health.status),
            "message": report.health.message,
        },
        "capabilities": {
            "earliest_daily_bar_date": (
                report.capabilities.earliest_daily_bar_date.isoformat()
                if report.capabilities.earliest_daily_bar_date is not None
                else None
            ),
            "supports_delisted": report.capabilities.supports_delisted,
            "supports_symbol_history": report.capabilities.supports_symbol_history,
            "known_limitations": list(report.capabilities.known_limitations),
        },
        "checks": [
            {
                "check_id": check.check_id,
                "state": str(check.state),
                "detail": check.detail,
            }
            for check in report.checks
        ],
        "cases": [
            {
                "case_id": case.case_id,
                "automated_gate_passed": case.automated_gate_passed,
                "daily_bar_count": case.daily_bar_count,
                "corporate_action_count": case.corporate_action_count,
                "normalization_status": (
                    str(case.normalization_status) if case.normalization_status is not None else None
                ),
                "checks": [
                    {
                        "check_id": check.check_id,
                        "state": str(check.state),
                        "detail": check.detail,
                    }
                    for check in case.checks
                ],
            }
            for case in report.cases
        ],
        "unresolved_manual_gates": list(report.unresolved_manual_gates),
    }


def _exception_record(exc: Exception) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _instrument_snapshot(instrument: ProviderInstrument) -> dict[str, object]:
    return {
        "provider_instrument_id": instrument.provider_instrument_id,
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "active": instrument.active,
        "first_trade_date": (
            instrument.first_trade_date.isoformat()
            if instrument.first_trade_date is not None
            else None
        ),
        "end_date": instrument.end_date.isoformat() if instrument.end_date is not None else None,
    }


def run_evaluation(*, api_key: str, report_path: Path, raw_root: Path) -> bool:
    """Execute the real sample and write a sanitized machine-readable evidence report."""

    started_at = datetime.now(UTC)
    adapter = MassiveAdapter.from_api_key(api_key, raw_root=raw_root)
    output: dict[str, Any] = {
        "evaluation_version": str(_EVALUATION_VERSION),
        "started_at": started_at.isoformat(),
        "provider_id": adapter.provider_id,
        "sample_design": [spec.case_id for spec in _SAMPLE_SPECS],
        "cases": [],
        "fatal_error": None,
    }

    try:
        instruments = tuple(adapter.get_instruments(as_of=None))
    except Exception as exc:  # noqa: BLE001 - evidence runner must persist provider failures
        output["fatal_error"] = _exception_record(exc)
        output["finished_at"] = datetime.now(UTC).isoformat()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
        return False

    output["instrument_inventory_count"] = len(instruments)
    cached_adapter = _CachedInstrumentAdapter(adapter, instruments)
    automated_results: list[bool] = []
    unresolved_gates: set[str] = set()

    for spec in _SAMPLE_SPECS:
        matches = tuple(instrument for instrument in instruments if instrument.symbol == spec.symbol)
        case_output: dict[str, Any] = {
            "case_id": spec.case_id,
            "symbol": spec.symbol,
            "date_range": [spec.start.isoformat(), spec.end.isoformat()],
            "inventory_match_count": len(matches),
        }
        if len(matches) != 1:
            case_output["discovery_error"] = (
                f"expected one current/inactive inventory record for {spec.symbol}; "
                f"found {len(matches)}"
            )
            case_output["automated_gate_passed"] = False
            automated_results.append(False)
            output["cases"].append(case_output)
            continue

        instrument = matches[0]
        case_output["instrument"] = _instrument_snapshot(instrument)
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

        try:
            report = evaluate_provider_adapter(
                cached_adapter,
                (case,),
                dataset_version=_EVALUATION_VERSION,
            )
        except Exception as exc:  # noqa: BLE001 - preserve failed real-provider evidence
            case_output["execution_error"] = _exception_record(exc)
            case_output["automated_gate_passed"] = False
            automated_results.append(False)
        else:
            rendered = _report_to_dict(report)
            case_output["evaluation"] = rendered
            case_output["automated_gate_passed"] = report.automated_gate_passed
            automated_results.append(report.automated_gate_passed)
            unresolved_gates.update(report.unresolved_manual_gates)

        output["cases"].append(case_output)

    raw_manifest_count = sum(1 for _ in raw_root.rglob("manifest.json")) if raw_root.exists() else 0
    output["raw_response_manifest_count"] = raw_manifest_count
    output["raw_bytes_uploaded_as_artifact"] = False
    output["automated_gate_passed"] = bool(automated_results) and all(automated_results)
    output["provider_accepted"] = False
    output["unresolved_manual_gates"] = sorted(unresolved_gates)
    output["scientific_gaps"] = [
        "licensing/storage rights still require explicit confirmation",
        "correction/revision behavior requires comparison across separated retrieval times",
        "first-trade/IPO boundary evidence remains unresolved where provider reference data omit it",
        "secondary-provider reconciliation has not yet been run on this live sample",
    ]
    output["finished_at"] = datetime.now(UTC).isoformat()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return bool(output["automated_gate_passed"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    api_key = os.environ.get("MASSIVE_API_KEY", "")
    if not api_key.strip():
        raise SystemExit("MASSIVE_API_KEY is required")
    passed = run_evaluation(api_key=api_key, report_path=args.report, raw_root=args.raw_root)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
