"""Quota-aware Tiingo acquisition campaign for an explicit S&P 500 snapshot.

This module stages raw provider evidence only. It never promotes ticker identity into the
canonical instrument master and never writes canonical bars. The universe snapshot is
externally sourced but must match an explicit expected date and row count before any Tiingo
request is made.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote

from trade_scout.data.providers.tiingo import TiingoJsonClient


class TiingoSp500CampaignError(RuntimeError):
    """Raised when campaign configuration, universe evidence, or state is invalid."""


@dataclass(frozen=True, slots=True)
class TiingoSp500CampaignPlan:
    """Versioned acquisition plan with a fail-closed universe snapshot contract."""

    plan_version: str
    universe_source_url: str
    expected_snapshot_date: date
    expected_constituent_count: int
    history_start: date
    history_end: date
    max_symbols_per_run: int


@dataclass(frozen=True, slots=True)
class TiingoSp500UniverseSnapshot:
    """Validated current-universe evidence used only to scope acquisition."""

    snapshot_date: date
    symbols: tuple[str, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class TiingoSp500CampaignRun:
    """One bounded campaign invocation."""

    plan_version: str
    universe_sha256: str
    completed_symbol_count: int
    pending_symbol_count: int
    executed_symbol_count: int
    acquired_row_count: int
    rate_limited: bool
    rate_limited_symbol: str | None
    failed_symbol: str | None
    failure_type: str | None


def load_tiingo_sp500_campaign_plan(path: Path) -> TiingoSp500CampaignPlan:
    """Load the checked-in v0.1 plan and reject unknown structure."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoSp500CampaignError(f"cannot read Tiingo S&P 500 plan: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoSp500CampaignError("Tiingo S&P 500 plan is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TiingoSp500CampaignError("Tiingo S&P 500 plan root must be an object")
    required = {
        "schema_version",
        "plan_version",
        "universe_source_url",
        "expected_snapshot_date",
        "expected_constituent_count",
        "history_start",
        "history_end",
        "max_symbols_per_run",
    }
    if set(payload) != required:
        raise TiingoSp500CampaignError("Tiingo S&P 500 plan has missing or unknown fields")
    if payload["schema_version"] != "tiingo-sp500-campaign-v0.1":
        raise TiingoSp500CampaignError("unsupported Tiingo S&P 500 campaign schema")
    try:
        plan = TiingoSp500CampaignPlan(
            plan_version=_required_text(payload["plan_version"], "plan_version"),
            universe_source_url=_required_text(
                payload["universe_source_url"], "universe_source_url"
            ),
            expected_snapshot_date=date.fromisoformat(
                _required_text(payload["expected_snapshot_date"], "expected_snapshot_date")
            ),
            expected_constituent_count=_required_positive_int(
                payload["expected_constituent_count"], "expected_constituent_count"
            ),
            history_start=date.fromisoformat(
                _required_text(payload["history_start"], "history_start")
            ),
            history_end=date.fromisoformat(_required_text(payload["history_end"], "history_end")),
            max_symbols_per_run=_required_positive_int(
                payload["max_symbols_per_run"], "max_symbols_per_run"
            ),
        )
    except ValueError as exc:
        raise TiingoSp500CampaignError("Tiingo S&P 500 campaign contains invalid dates") from exc
    if plan.history_end < plan.history_start:
        raise TiingoSp500CampaignError("Tiingo campaign history_end precedes history_start")
    return plan


def parse_tiingo_sp500_universe(
    payload: bytes,
    plan: TiingoSp500CampaignPlan,
) -> TiingoSp500UniverseSnapshot:
    """Validate an external constituent CSV before it may scope provider calls."""

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TiingoSp500CampaignError("S&P 500 universe CSV is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    required_columns = {"symbol", "date"}
    if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
        raise TiingoSp500CampaignError("S&P 500 universe CSV lacks symbol/date columns")
    symbols: list[str] = []
    observed_dates: set[date] = set()
    for row in reader:
        raw_symbol = (row.get("symbol") or "").strip()
        raw_date = (row.get("date") or "").strip()
        if not raw_symbol or not raw_date:
            raise TiingoSp500CampaignError("S&P 500 universe contains blank symbol/date")
        try:
            observed_dates.add(date.fromisoformat(raw_date))
        except ValueError as exc:
            raise TiingoSp500CampaignError("S&P 500 universe contains invalid snapshot date") from exc
        symbols.append(raw_symbol.upper())
    if observed_dates != {plan.expected_snapshot_date}:
        raise TiingoSp500CampaignError(
            "S&P 500 universe snapshot date does not match checked-in campaign plan"
        )
    if len(symbols) != plan.expected_constituent_count:
        raise TiingoSp500CampaignError(
            "S&P 500 universe constituent count does not match checked-in campaign plan"
        )
    if len(set(symbols)) != len(symbols):
        raise TiingoSp500CampaignError("S&P 500 universe contains duplicate symbols")
    return TiingoSp500UniverseSnapshot(
        snapshot_date=plan.expected_snapshot_date,
        symbols=tuple(sorted(symbols)),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def run_tiingo_sp500_campaign(
    client: TiingoJsonClient,
    plan: TiingoSp500CampaignPlan,
    snapshot: TiingoSp500UniverseSnapshot,
    state_path: Path,
    *,
    max_symbols_this_run: int | None = None,
) -> TiingoSp500CampaignRun:
    """Acquire a bounded number of full-history symbols and checkpoint each success."""

    budget = max_symbols_this_run or plan.max_symbols_per_run
    if budget < 1:
        raise ValueError("max_symbols_this_run must be positive")
    completed = _load_completed(state_path, plan, snapshot)
    executed = 0
    rows_acquired = 0
    rate_limited_symbol: str | None = None
    failed_symbol: str | None = None
    failure_type: str | None = None

    for symbol in snapshot.symbols:
        if symbol in completed:
            continue
        if executed >= budget:
            break
        try:
            response = client.get_json(
                f"/tiingo/daily/{quote(symbol, safe='')}/prices",
                {
                    "startDate": plan.history_start.isoformat(),
                    "endDate": plan.history_end.isoformat(),
                    "resampleFreq": "daily",
                },
            )
        except Exception as exc:
            if _is_http_429(exc):
                rate_limited_symbol = symbol
            else:
                failed_symbol = symbol
                failure_type = type(exc).__name__
            break
        if not isinstance(response, list) or not all(isinstance(item, dict) for item in response):
            failed_symbol = symbol
            failure_type = "TiingoResponseShapeError"
            break
        completed.add(symbol)
        executed += 1
        rows_acquired += len(response)
        _persist_completed(state_path, plan, snapshot, completed)

    pending = len(snapshot.symbols) - len(completed)
    return TiingoSp500CampaignRun(
        plan_version=plan.plan_version,
        universe_sha256=snapshot.sha256,
        completed_symbol_count=len(completed),
        pending_symbol_count=pending,
        executed_symbol_count=executed,
        acquired_row_count=rows_acquired,
        rate_limited=rate_limited_symbol is not None,
        rate_limited_symbol=rate_limited_symbol,
        failed_symbol=failed_symbol,
        failure_type=failure_type,
    )


def _load_completed(
    path: Path,
    plan: TiingoSp500CampaignPlan,
    snapshot: TiingoSp500UniverseSnapshot,
) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TiingoSp500CampaignError("Tiingo campaign checkpoint is unreadable") from exc
    if not isinstance(payload, dict):
        raise TiingoSp500CampaignError("Tiingo campaign checkpoint must be an object")
    if payload.get("plan_version") != plan.plan_version:
        raise TiingoSp500CampaignError("Tiingo checkpoint belongs to another campaign plan")
    if payload.get("universe_sha256") != snapshot.sha256:
        raise TiingoSp500CampaignError("Tiingo checkpoint belongs to another universe snapshot")
    raw_completed = payload.get("completed_symbols")
    if not isinstance(raw_completed, list) or not all(isinstance(item, str) for item in raw_completed):
        raise TiingoSp500CampaignError("Tiingo checkpoint completed_symbols is invalid")
    completed = set(raw_completed)
    if not completed.issubset(set(snapshot.symbols)):
        raise TiingoSp500CampaignError("Tiingo checkpoint references a symbol outside the snapshot")
    return completed


def _persist_completed(
    path: Path,
    plan: TiingoSp500CampaignPlan,
    snapshot: TiingoSp500UniverseSnapshot,
    completed: set[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan_version": plan.plan_version,
        "universe_sha256": snapshot.sha256,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "completed_symbols": [symbol for symbol in snapshot.symbols if symbol in completed],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _is_http_429(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, HTTPError) and current.code == 429:
            return True
        current = current.__cause__ or current.__context__
    return False


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoSp500CampaignError(f"{field} must be non-empty text")
    return value.strip()


def _required_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TiingoSp500CampaignError(f"{field} must be a positive integer")
    return value
