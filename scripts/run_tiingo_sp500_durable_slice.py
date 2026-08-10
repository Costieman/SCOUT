"""Run a Tiingo S&P 500 slice only when raw evidence can survive the process.

A symbol becomes durably complete only after its exact raw response is checksum-verified,
a metadata-only durable receipt is written, and the safe campaign state is advanced. GitHub-hosted
runners are rejected because their filesystem is ephemeral.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from trade_scout.data.durable_raw_receipt import (
    create_durable_raw_receipt,
    persist_durable_raw_receipt,
    verify_durable_raw_receipt,
)
from trade_scout.data.providers.tiingo import TiingoHttpClient
from trade_scout.data.providers.tiingo_campaign_state import (
    RawStorageClass,
    TiingoSafeCampaignState,
    advance_tiingo_safe_campaign_state,
    initial_tiingo_safe_campaign_state,
    load_tiingo_safe_campaign_state,
    persist_tiingo_safe_campaign_state,
)
from trade_scout.data.providers.tiingo_receipt_capture import TiingoReceiptTrackingCapture
from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignRun,
    load_tiingo_sp500_campaign_plan,
    parse_tiingo_sp500_universe,
)
from trade_scout.data.providers.tiingo_symbology import build_tiingo_query_symbol_links
from trade_scout.data.raw_store import RawBatchStore

CAMPAIGN_ID = "tiingo-sp500-baseline-v0.1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )
    parser.add_argument("--durable-root", type=Path, required=True)
    parser.add_argument("--storage-namespace", required=True)
    parser.add_argument("--max-symbols", type=int, default=1)
    args = parser.parse_args()

    if os.environ.get("RUNNER_ENVIRONMENT", "").strip().lower() == "github-hosted":
        raise SystemExit(
            "durable Tiingo acquisition is forbidden on GitHub-hosted ephemeral runners"
        )
    if args.max_symbols < 1:
        raise SystemExit("--max-symbols must be positive")

    token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("TIINGO_API_TOKEN is not configured")

    plan = load_tiingo_sp500_campaign_plan(args.plan)
    universe_request = Request(
        plan.universe_source_url,
        headers={"User-Agent": "trade-scout/0.1"},
    )
    with urlopen(universe_request, timeout=30.0) as response:
        universe_payload = bytes(response.read())
    snapshot = parse_tiingo_sp500_universe(universe_payload, plan)
    symbol_links = build_tiingo_query_symbol_links(snapshot.symbols)

    durable_root = args.durable_root.resolve()
    raw_root = durable_root / "raw"
    receipt_root = durable_root / "receipts"
    state_path = durable_root / "safe-state.json"
    state = _load_or_initialize_state(state_path, plan.plan_version, snapshot)
    _validate_state_identity(state, plan.plan_version, snapshot.sha256, len(snapshot.symbols))

    capture = TiingoReceiptTrackingCapture(RawBatchStore(raw_root))
    client = TiingoHttpClient(token, raw_capture=capture)
    completed = set(state.durable_completed_symbols)
    executed = 0

    for link in symbol_links:
        source_symbol = link.source_symbol
        if source_symbol in completed:
            continue
        if executed >= args.max_symbols:
            break

        endpoint = f"/tiingo/daily/{quote(link.query_symbol, safe='')}/prices"
        before_capture_count = len(capture.captured_records)
        try:
            response = client.get_json(
                endpoint,
                {
                    "startDate": plan.history_start.isoformat(),
                    "endDate": plan.history_end.isoformat(),
                    "resampleFreq": "daily",
                },
            )
        except Exception as exc:
            rate_limited = _is_http_429(exc)
            run = _run_result(
                plan.plan_version,
                snapshot.sha256,
                len(completed),
                len(snapshot.symbols),
                rate_limited_symbol=source_symbol if rate_limited else None,
                failed_symbol=None if rate_limited else source_symbol,
                failure_type=None if rate_limited else type(exc).__name__,
            )
            state = advance_tiingo_safe_campaign_state(
                state,
                run=run,
                snapshot=snapshot,
                storage_class=RawStorageClass.DURABLE,
                completed_symbols_after_run=tuple(sorted(completed)),
                durable_row_count_this_run=0,
                observed_at=datetime.now(UTC),
            )
            persist_tiingo_safe_campaign_state(state_path, state)
            return 0 if rate_limited else 1

        if (
            not isinstance(response, list)
            or not response
            or not all(isinstance(item, dict) for item in response)
        ):
            _persist_failure(
                state,
                snapshot=snapshot,
                completed=completed,
                plan_version=plan.plan_version,
                symbol=source_symbol,
                failure_type="EmptyOrInvalidTiingoHistory",
                state_path=state_path,
            )
            return 1

        new_records = capture.captured_records[before_capture_count:]
        if len(new_records) != 1:
            _persist_failure(
                state,
                snapshot=snapshot,
                completed=completed,
                plan_version=plan.plan_version,
                symbol=source_symbol,
                failure_type="UnexpectedRawCaptureCount",
                state_path=state_path,
            )
            return 1
        record = new_records[0]
        if record.manifest.endpoint != endpoint:
            _persist_failure(
                state,
                snapshot=snapshot,
                completed=completed,
                plan_version=plan.plan_version,
                symbol=source_symbol,
                failure_type="RawCaptureEndpointMismatch",
                state_path=state_path,
            )
            return 1

        receipt = create_durable_raw_receipt(
            record,
            durable_root=raw_root,
            storage_namespace=args.storage_namespace,
            subject_key=source_symbol,
        )
        verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace=args.storage_namespace,
        )
        receipt_path = receipt_root / source_symbol / f"{receipt.receipt_id}.json"
        persist_durable_raw_receipt(receipt_path, receipt)

        completed.add(source_symbol)
        executed += 1
        row_count = len(response)
        run = TiingoSp500CampaignRun(
            plan_version=plan.plan_version,
            universe_sha256=snapshot.sha256,
            completed_symbol_count=len(completed),
            pending_symbol_count=len(snapshot.symbols) - len(completed),
            executed_symbol_count=1,
            acquired_row_count=row_count,
            rate_limited=False,
            rate_limited_symbol=None,
            failed_symbol=None,
            failure_type=None,
        )
        state = advance_tiingo_safe_campaign_state(
            state,
            run=run,
            snapshot=snapshot,
            storage_class=RawStorageClass.DURABLE,
            completed_symbols_after_run=tuple(sorted(completed)),
            durable_row_count_this_run=row_count,
            observed_at=datetime.now(UTC),
        )
        persist_tiingo_safe_campaign_state(state_path, state)

    print(state_path)
    return 0


def _load_or_initialize_state(
    path: Path,
    plan_version: str,
    snapshot,
) -> TiingoSafeCampaignState:
    if path.exists():
        return load_tiingo_safe_campaign_state(path)
    state = initial_tiingo_safe_campaign_state(
        campaign_id=CAMPAIGN_ID,
        plan_version=plan_version,
        snapshot=snapshot,
    )
    persist_tiingo_safe_campaign_state(path, state)
    return state


def _validate_state_identity(
    state: TiingoSafeCampaignState,
    plan_version: str,
    universe_sha256: str,
    total_symbols: int,
) -> None:
    if state.campaign_id != CAMPAIGN_ID:
        raise SystemExit("durable state belongs to another campaign")
    if state.plan_version != plan_version:
        raise SystemExit("durable state belongs to another plan version")
    if state.universe_sha256 != universe_sha256:
        raise SystemExit("durable state belongs to another S&P 500 universe snapshot")
    if state.total_symbol_count != total_symbols:
        raise SystemExit("durable state symbol count conflicts with the universe snapshot")


def _persist_failure(
    state: TiingoSafeCampaignState,
    *,
    snapshot,
    completed: set[str],
    plan_version: str,
    symbol: str,
    failure_type: str,
    state_path: Path,
) -> TiingoSafeCampaignState:
    run = _run_result(
        plan_version,
        snapshot.sha256,
        len(completed),
        len(snapshot.symbols),
        failed_symbol=symbol,
        failure_type=failure_type,
    )
    updated = advance_tiingo_safe_campaign_state(
        state,
        run=run,
        snapshot=snapshot,
        storage_class=RawStorageClass.DURABLE,
        completed_symbols_after_run=tuple(sorted(completed)),
        durable_row_count_this_run=0,
        observed_at=datetime.now(UTC),
    )
    persist_tiingo_safe_campaign_state(state_path, updated)
    return updated


def _run_result(
    plan_version: str,
    universe_sha256: str,
    completed_count: int,
    total_count: int,
    *,
    rate_limited_symbol: str | None = None,
    failed_symbol: str | None = None,
    failure_type: str | None = None,
) -> TiingoSp500CampaignRun:
    return TiingoSp500CampaignRun(
        plan_version=plan_version,
        universe_sha256=universe_sha256,
        completed_symbol_count=completed_count,
        pending_symbol_count=total_count - completed_count,
        executed_symbol_count=0,
        acquired_row_count=0,
        rate_limited=rate_limited_symbol is not None,
        rate_limited_symbol=rate_limited_symbol,
        failed_symbol=failed_symbol,
        failure_type=failure_type,
    )


def _is_http_429(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, HTTPError) and current.code == 429:
            return True
        current = current.__cause__ or current.__context__
    return False


if __name__ == "__main__":
    raise SystemExit(main())
