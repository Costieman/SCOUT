"""Run the agreed real Massive sample without exposing credentials or raw vendor bytes."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from trade_scout.data.contracts import (
    CorporateActionType,
    DatasetVersion,
    SecurityType,
)
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
from trade_scout.data.providers.massive import (
    MassiveAdapter,
    MassiveApiError,
    MassiveHttpClient,
    RawStoreCapture,
)
from trade_scout.data.raw_store import Primitive, RawBatchStore

_EVALUATION_VERSION = DatasetVersion("massive-live-evaluation-2026-08-08-v2")


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


class _RateLimitedTransport:
    """Respect provider throttling while keeping request URLs and credentials out of logs."""

    def __init__(self, *, max_attempts: int = 8, fallback_retry_seconds: float = 13.0) -> None:
        self.max_attempts = max_attempts
        self.fallback_retry_seconds = fallback_retry_seconds

    def get(self, url: str, *, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "application/json"})
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urlopen(request, timeout=timeout) as response:
                    return bytes(response.read())
            except HTTPError as exc:
                if exc.code == 429 and attempt < self.max_attempts:
                    time.sleep(self._retry_delay(exc, attempt))
                    continue
                if 500 <= exc.code < 600 and attempt < self.max_attempts:
                    time.sleep(min(2.0**attempt, 30.0))
                    continue
                raise MassiveApiError(f"Massive HTTP error {exc.code}") from exc
            except URLError as exc:
                if attempt < self.max_attempts:
                    time.sleep(min(2.0**attempt, 30.0))
                    continue
                raise MassiveApiError(f"Massive network error: {exc.reason}") from exc
        raise MassiveApiError("Massive request exhausted retry policy")

    def _retry_delay(self, exc: HTTPError, attempt: int) -> float:
        retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
        if retry_after is not None:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        return self.fallback_retry_seconds * min(attempt, 3)


class _CachingJsonClient:
    """Cache non-aggregate reference evidence while repeating price retrievals live."""

    def __init__(self, client: MassiveHttpClient) -> None:
        self._client = client
        self._cache: dict[tuple[str, tuple[tuple[str, Primitive], ...]], Mapping[str, object]] = {}

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, Primitive] | None = None,
    ) -> Mapping[str, object]:
        params = dict(parameters or {})
        if endpoint.startswith("/v2/aggs/"):
            return self._client.get_json(endpoint, params)
        key = (endpoint, tuple(sorted(params.items(), key=lambda item: item[0])))
        cached = self._cache.get(key)
        if cached is None:
            cached = self._client.get_json(endpoint, params)
            self._cache[key] = cached
        return cached


class _CachedInstrumentAdapter:
    """Delegate to a real adapter while reusing targeted instrument and health evidence."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        instruments: tuple[ProviderInstrument, ...],
        capabilities: ProviderCapabilities,
        health: ProviderHealth,
    ) -> None:
        self.provider_id = adapter.provider_id
        self._adapter = adapter
        self._instruments = instruments
        self._capabilities = capabilities
        self._health = health

    def describe_capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def health_check(self) -> ProviderHealth:
        return self._health

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


def _discover_instrument(client: _CachingJsonClient, symbol: str) -> ProviderInstrument:
    matches: dict[str, ProviderInstrument] = {}
    for active in (True, False):
        response = client.get_json(
            "/v3/reference/tickers",
            {
                "ticker": symbol,
                "market": "stocks",
                "type": "CS",
                "active": active,
                "limit": 10,
            },
        )
        results = response.get("results", [])
        if not isinstance(results, list):
            raise MassiveApiError("Massive targeted ticker results must be a list")
        for raw_item in results:
            if not isinstance(raw_item, dict):
                raise MassiveApiError("Massive targeted ticker result must be an object")
            item = cast(Mapping[str, object], raw_item)
            if item.get("ticker") != symbol:
                continue
            provider_instrument_id = _stable_id(item)
            if provider_instrument_id is None:
                continue
            instrument = _provider_instrument_from_reference(item, provider_instrument_id)
            matches[provider_instrument_id] = instrument

    if len(matches) != 1:
        raise MassiveApiError(
            f"expected one stable current/inactive identity for {symbol}; found {len(matches)}"
        )
    return next(iter(matches.values()))


def _stable_id(item: Mapping[str, object]) -> str | None:
    composite = item.get("composite_figi")
    if isinstance(composite, str) and composite:
        return composite
    share_class = item.get("share_class_figi")
    if isinstance(share_class, str) and share_class:
        return share_class
    return None


def _provider_instrument_from_reference(
    item: Mapping[str, object],
    provider_instrument_id: str,
) -> ProviderInstrument:
    symbol = _required_string(item, "ticker")
    name = _required_string(item, "name")
    exchange = _required_string(item, "primary_exchange")
    active = item.get("active")
    if not isinstance(active, bool):
        raise MassiveApiError("Massive targeted ticker active field must be boolean")
    currency_value = item.get("currency_symbol") or item.get("currency_name")
    if not isinstance(currency_value, str) or not currency_value:
        raise MassiveApiError("Massive targeted ticker currency is unavailable")

    source_fields: dict[str, str | int | float | bool | None] = {}
    for key, value in item.items():
        if value is None or isinstance(value, str | int | float | bool):
            source_fields[key] = value

    end_date = _optional_date(item.get("delisted_utc"))
    return ProviderInstrument(
        provider_id="massive",
        provider_instrument_id=provider_instrument_id,
        symbol=symbol,
        name=name,
        exchange=exchange,
        security_type=SecurityType.COMMON_STOCK,
        currency=currency_value.upper(),
        active=active,
        first_trade_date=None,
        end_date=end_date,
        source_fields=source_fields,
    )


def _required_string(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise MassiveApiError(f"Massive targeted ticker field {key} must be a string")
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MassiveApiError("Massive targeted ticker date must be a string or null")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise MassiveApiError("Massive targeted ticker date is invalid") from exc


def _write_report(path: Path, output: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


def run_evaluation(*, api_key: str, report_path: Path, raw_root: Path) -> bool:
    """Execute the real sample and write a sanitized machine-readable evidence report."""

    started_at = datetime.now(UTC)
    raw_store = RawBatchStore(raw_root)
    raw_capture = RawStoreCapture(raw_store)
    http_client = MassiveHttpClient(
        api_key,
        transport=_RateLimitedTransport(),
        raw_capture=raw_capture,
        timeout=30.0,
    )
    client = _CachingJsonClient(http_client)
    adapter = MassiveAdapter(client)
    output: dict[str, Any] = {
        "evaluation_version": str(_EVALUATION_VERSION),
        "started_at": started_at.isoformat(),
        "provider_id": adapter.provider_id,
        "sample_design": [spec.case_id for spec in _SAMPLE_SPECS],
        "cases": [],
        "fatal_error": None,
    }

    try:
        capabilities = adapter.describe_capabilities()
        health = adapter.health_check()
        instruments = tuple(_discover_instrument(client, spec.symbol) for spec in _SAMPLE_SPECS)
    except Exception as exc:  # noqa: BLE001 - evidence runner must persist provider failures
        output["fatal_error"] = _exception_record(exc)
        output["finished_at"] = datetime.now(UTC).isoformat()
        _write_report(report_path, output)
        return False

    output["targeted_instrument_count"] = len(instruments)
    cached_adapter = _CachedInstrumentAdapter(adapter, instruments, capabilities, health)
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
                f"expected one targeted inventory record for {spec.symbol}; found {len(matches)}"
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
            case_output["evaluation"] = _report_to_dict(report)
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

    _write_report(report_path, output)
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
