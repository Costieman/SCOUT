"""Advance the safe Tiingo S&P 500 campaign ledger from one derived run report.

This script never reads provider payload values. Hosted GitHub runners must use
``--storage-class ephemeral``; only callers with a genuinely durable raw-data root may use
``durable`` and advance completed-symbol or durable-row counters.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from trade_scout.data.providers.tiingo_campaign_state import (
    RawStorageClass,
    advance_tiingo_safe_campaign_state,
    initial_tiingo_safe_campaign_state,
    load_tiingo_safe_campaign_state,
    persist_tiingo_safe_campaign_state,
)
from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignRun,
    load_tiingo_sp500_campaign_plan,
    parse_tiingo_sp500_universe,
)

CAMPAIGN_ID = "tiingo-sp500"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--previous-state", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--storage-class",
        choices=[item.value for item in RawStorageClass],
        default=RawStorageClass.EPHEMERAL.value,
    )
    args = parser.parse_args()

    plan = load_tiingo_sp500_campaign_plan(args.plan)
    request = Request(plan.universe_source_url, headers={"User-Agent": "trade-scout/0.1"})
    with urlopen(request, timeout=30.0) as response:
        universe_payload = bytes(response.read())
    snapshot = parse_tiingo_sp500_universe(universe_payload, plan)

    previous = (
        load_tiingo_safe_campaign_state(args.previous_state)
        if args.previous_state is not None and args.previous_state.is_file()
        else initial_tiingo_safe_campaign_state(
            campaign_id=CAMPAIGN_ID,
            plan_version=plan.plan_version,
            snapshot=snapshot,
        )
    )
    run = _load_run(args.report)
    storage_class = RawStorageClass(args.storage_class)

    if storage_class is RawStorageClass.DURABLE:
        if args.checkpoint is None or not args.checkpoint.is_file():
            raise SystemExit("durable state advancement requires a campaign checkpoint")
        completed = _load_completed(args.checkpoint, plan.plan_version, snapshot.sha256)
        new_durable_symbols = set(completed) - set(previous.durable_completed_symbols)
        if not new_durable_symbols and run.acquired_row_count:
            raise SystemExit(
                "run reported acquired rows but durable checkpoint has no newly completed symbols"
            )
        durable_rows = run.acquired_row_count
    else:
        completed = previous.durable_completed_symbols
        durable_rows = 0

    updated = advance_tiingo_safe_campaign_state(
        previous,
        run=run,
        snapshot=snapshot,
        storage_class=storage_class,
        completed_symbols_after_run=tuple(completed),
        durable_row_count_this_run=durable_rows,
        observed_at=datetime.now(UTC),
    )
    persist_tiingo_safe_campaign_state(args.output, updated)
    print(args.output)
    return 0


def _load_run(path: Path) -> TiingoSp500CampaignRun:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read Tiingo campaign report: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Tiingo campaign report must be an object")
    return TiingoSp500CampaignRun(
        plan_version=_text(payload, "plan_version"),
        universe_sha256=_text(payload, "universe_sha256"),
        completed_symbol_count=_integer(payload, "completed_symbol_count"),
        pending_symbol_count=_integer(payload, "pending_symbol_count"),
        executed_symbol_count=_integer(payload, "executed_symbol_count"),
        acquired_row_count=_integer(payload, "acquired_row_count"),
        rate_limited=_boolean(payload, "rate_limited"),
        rate_limited_symbol=_optional_text(payload.get("rate_limited_symbol")),
        failed_symbol=_optional_text(payload.get("failed_symbol")),
        failure_type=_optional_text(payload.get("failure_type")),
    )


def _load_completed(path: Path, plan_version: str, universe_sha256: str) -> tuple[str, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read Tiingo campaign checkpoint: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Tiingo campaign checkpoint must be an object")
    if payload.get("plan_version") != plan_version:
        raise SystemExit("Tiingo campaign checkpoint belongs to another plan")
    if payload.get("universe_sha256") != universe_sha256:
        raise SystemExit("Tiingo campaign checkpoint belongs to another universe")
    completed = payload.get("completed_symbols")
    if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
        raise SystemExit("Tiingo campaign checkpoint completed_symbols is invalid")
    return tuple(completed)


def _text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Tiingo campaign report {field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SystemExit("Tiingo campaign optional text field is invalid")
    return value.strip()


def _integer(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SystemExit(f"Tiingo campaign report {field} must be a non-negative integer")
    return value


def _boolean(payload: dict[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise SystemExit(f"Tiingo campaign report {field} must be boolean")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
