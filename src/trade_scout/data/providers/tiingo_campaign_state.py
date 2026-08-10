"""Safe, monotonic campaign-state ledger for staged Tiingo acquisition.

The ledger intentionally contains no provider payload values and no credentials. It can be
persisted in a public Git branch because it records only campaign control metadata. A symbol is
considered durably completed only when the caller explicitly declares that its raw evidence was
written to storage expected to survive the process that performed the provider request.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignRun,
    TiingoSp500UniverseSnapshot,
)


class TiingoCampaignStateError(ValueError):
    """Raised when persisted safe state is malformed or conflicts with campaign identity."""


class RawStorageClass(StrEnum):
    """Durability contract for raw provider evidence produced by one campaign run."""

    EPHEMERAL = "ephemeral"
    DURABLE = "durable"


@dataclass(frozen=True, slots=True)
class TiingoSafeCampaignState:
    """Persistable campaign control metadata with no licensed market-data values."""

    schema_version: str
    campaign_id: str
    plan_version: str
    universe_sha256: str
    snapshot_date: date
    total_symbol_count: int
    durable_completed_symbols: tuple[str, ...]
    run_count: int
    observed_row_count_total: int
    durable_row_count_total: int
    quota_pause_count: int
    failure_count: int
    last_run_at: datetime | None
    last_status: str
    last_rate_limited_symbol: str | None
    last_failed_symbol: str | None
    last_failure_type: str | None

    @property
    def durable_completed_symbol_count(self) -> int:
        return len(self.durable_completed_symbols)

    @property
    def durable_pending_symbol_count(self) -> int:
        return self.total_symbol_count - self.durable_completed_symbol_count


def initial_tiingo_safe_campaign_state(
    *,
    campaign_id: str,
    plan_version: str,
    snapshot: TiingoSp500UniverseSnapshot,
) -> TiingoSafeCampaignState:
    """Create empty safe state for one exact plan and universe snapshot."""

    if not campaign_id.strip():
        raise TiingoCampaignStateError("campaign_id must be non-empty")
    if not plan_version.strip():
        raise TiingoCampaignStateError("plan_version must be non-empty")
    return TiingoSafeCampaignState(
        schema_version="tiingo-safe-campaign-state-v0.1",
        campaign_id=campaign_id.strip(),
        plan_version=plan_version.strip(),
        universe_sha256=snapshot.sha256,
        snapshot_date=snapshot.snapshot_date,
        total_symbol_count=len(snapshot.symbols),
        durable_completed_symbols=(),
        run_count=0,
        observed_row_count_total=0,
        durable_row_count_total=0,
        quota_pause_count=0,
        failure_count=0,
        last_run_at=None,
        last_status="NOT_STARTED",
        last_rate_limited_symbol=None,
        last_failed_symbol=None,
        last_failure_type=None,
    )


def advance_tiingo_safe_campaign_state(
    previous: TiingoSafeCampaignState,
    *,
    run: TiingoSp500CampaignRun,
    snapshot: TiingoSp500UniverseSnapshot,
    storage_class: RawStorageClass,
    completed_symbols_after_run: tuple[str, ...],
    durable_row_count_this_run: int,
    observed_at: datetime,
) -> TiingoSafeCampaignState:
    """Advance safe state without allowing ephemeral work to masquerade as durable progress."""

    _validate_identity(previous, run=run, snapshot=snapshot)
    _validate_timestamp(observed_at)
    if durable_row_count_this_run < 0:
        raise TiingoCampaignStateError("durable_row_count_this_run cannot be negative")

    snapshot_symbols = set(snapshot.symbols)
    proposed = tuple(sorted(set(completed_symbols_after_run)))
    if not set(proposed).issubset(snapshot_symbols):
        raise TiingoCampaignStateError("completed symbols contain values outside the universe")
    prior = set(previous.durable_completed_symbols)
    if storage_class is RawStorageClass.EPHEMERAL:
        if set(proposed) != prior:
            raise TiingoCampaignStateError(
                "ephemeral runs cannot advance durable completed symbols"
            )
        if durable_row_count_this_run != 0:
            raise TiingoCampaignStateError("ephemeral runs cannot advance durable row counts")
    elif not prior.issubset(set(proposed)):
        raise TiingoCampaignStateError("durable completion state cannot move backwards")

    quota_pause_count = previous.quota_pause_count + int(run.rate_limited)
    failed = run.failed_symbol is not None
    failure_count = previous.failure_count + int(failed)
    if run.rate_limited:
        status = "PAUSED_RATE_LIMITED"
    elif failed:
        status = "FAILED"
    elif len(proposed) == len(snapshot.symbols):
        status = "COMPLETE"
    elif run.executed_symbol_count:
        status = "PROGRESSED"
    else:
        status = "NO_PROGRESS"

    return TiingoSafeCampaignState(
        schema_version=previous.schema_version,
        campaign_id=previous.campaign_id,
        plan_version=previous.plan_version,
        universe_sha256=previous.universe_sha256,
        snapshot_date=previous.snapshot_date,
        total_symbol_count=previous.total_symbol_count,
        durable_completed_symbols=proposed,
        run_count=previous.run_count + 1,
        observed_row_count_total=(previous.observed_row_count_total + run.acquired_row_count),
        durable_row_count_total=(previous.durable_row_count_total + durable_row_count_this_run),
        quota_pause_count=quota_pause_count,
        failure_count=failure_count,
        last_run_at=observed_at.astimezone(UTC),
        last_status=status,
        last_rate_limited_symbol=run.rate_limited_symbol,
        last_failed_symbol=run.failed_symbol,
        last_failure_type=run.failure_type,
    )


def load_tiingo_safe_campaign_state(path: Path) -> TiingoSafeCampaignState:
    """Load safe state and reject unknown fields or malformed values."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoCampaignStateError(f"cannot read campaign state: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoCampaignStateError("campaign state is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TiingoCampaignStateError("campaign state root must be an object")
    expected = {
        "schema_version",
        "campaign_id",
        "plan_version",
        "universe_sha256",
        "snapshot_date",
        "total_symbol_count",
        "durable_completed_symbols",
        "run_count",
        "observed_row_count_total",
        "durable_row_count_total",
        "quota_pause_count",
        "failure_count",
        "last_run_at",
        "last_status",
        "last_rate_limited_symbol",
        "last_failed_symbol",
        "last_failure_type",
    }
    if set(payload) != expected:
        raise TiingoCampaignStateError("campaign state contains missing or unknown fields")
    if payload["schema_version"] != "tiingo-safe-campaign-state-v0.1":
        raise TiingoCampaignStateError("unsupported campaign state schema_version")

    completed = payload["durable_completed_symbols"]
    if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
        raise TiingoCampaignStateError("durable_completed_symbols must be a string array")
    if len(completed) != len(set(completed)):
        raise TiingoCampaignStateError("durable_completed_symbols contains duplicates")

    last_run_at = payload["last_run_at"]
    try:
        parsed_last_run = datetime.fromisoformat(last_run_at) if last_run_at is not None else None
        snapshot_date = date.fromisoformat(
            _required_text(payload["snapshot_date"], "snapshot_date")
        )
    except ValueError as exc:
        raise TiingoCampaignStateError("campaign state contains invalid date/time fields") from exc
    if parsed_last_run is not None:
        _validate_timestamp(parsed_last_run)

    numeric_fields = (
        "total_symbol_count",
        "run_count",
        "observed_row_count_total",
        "durable_row_count_total",
        "quota_pause_count",
        "failure_count",
    )
    for field in numeric_fields:
        value = payload[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TiingoCampaignStateError(f"{field} must be a non-negative integer")

    state = TiingoSafeCampaignState(
        schema_version="tiingo-safe-campaign-state-v0.1",
        campaign_id=_required_text(payload["campaign_id"], "campaign_id"),
        plan_version=_required_text(payload["plan_version"], "plan_version"),
        universe_sha256=_required_text(payload["universe_sha256"], "universe_sha256"),
        snapshot_date=snapshot_date,
        total_symbol_count=payload["total_symbol_count"],
        durable_completed_symbols=tuple(completed),
        run_count=payload["run_count"],
        observed_row_count_total=payload["observed_row_count_total"],
        durable_row_count_total=payload["durable_row_count_total"],
        quota_pause_count=payload["quota_pause_count"],
        failure_count=payload["failure_count"],
        last_run_at=parsed_last_run,
        last_status=_required_text(payload["last_status"], "last_status"),
        last_rate_limited_symbol=_optional_text(payload["last_rate_limited_symbol"]),
        last_failed_symbol=_optional_text(payload["last_failed_symbol"]),
        last_failure_type=_optional_text(payload["last_failure_type"]),
    )
    if state.durable_completed_symbol_count > state.total_symbol_count:
        raise TiingoCampaignStateError("durable completed count exceeds total symbol count")
    return state


def persist_tiingo_safe_campaign_state(path: Path, state: TiingoSafeCampaignState) -> None:
    """Atomically persist only whitelisted safe campaign metadata."""

    payload = asdict(state)
    payload["snapshot_date"] = state.snapshot_date.isoformat()
    payload["last_run_at"] = state.last_run_at.isoformat() if state.last_run_at else None
    payload["durable_completed_symbols"] = list(state.durable_completed_symbols)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _validate_identity(
    state: TiingoSafeCampaignState,
    *,
    run: TiingoSp500CampaignRun,
    snapshot: TiingoSp500UniverseSnapshot,
) -> None:
    if state.plan_version != run.plan_version:
        raise TiingoCampaignStateError("campaign run belongs to a different plan")
    if state.universe_sha256 != run.universe_sha256 or state.universe_sha256 != snapshot.sha256:
        raise TiingoCampaignStateError("campaign run belongs to a different universe snapshot")
    if state.snapshot_date != snapshot.snapshot_date:
        raise TiingoCampaignStateError("campaign state snapshot date does not match universe")
    if state.total_symbol_count != len(snapshot.symbols):
        raise TiingoCampaignStateError("campaign state symbol count does not match universe")
    if not set(state.durable_completed_symbols).issubset(set(snapshot.symbols)):
        raise TiingoCampaignStateError("campaign state contains completed symbols outside universe")


def _validate_timestamp(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TiingoCampaignStateError("campaign timestamps must be timezone-aware")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoCampaignStateError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TiingoCampaignStateError("optional text fields must be null or non-empty text")
    return value.strip()
