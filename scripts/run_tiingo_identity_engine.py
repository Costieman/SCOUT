"""Run unattended SEC-backed identity triage across durable Tiingo histories.

This command is intentionally metadata-only: it reads the durable Tiingo profile and current reviewed
identity candidate, collects independent SEC evidence, checkpoints every completed symbol, and writes
a deterministic READY/DEFER report. It never calls Tiingo and never mutates canonical data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.identity_adjudication import (
    IdentityEvidence,
    IdentityEvidenceState,
    IdentityReviewInput,
    build_identity_batch_report,
    persist_identity_batch_report,
)
from trade_scout.data.providers.sec_identity import (
    SecHttpClient,
    collect_sec_identity_evidence,
    load_sec_company_catalog,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
)

_STRUCTURAL_COUNT_FIELDS = (
    "invalid_date_row_count",
    "duplicate_date_count",
    "non_monotonic_date_count",
    "missing_required_field_row_count",
    "invalid_numeric_row_count",
    "ohlc_invariant_violation_count",
    "negative_volume_count",
    "long_calendar_gap_count",
)
_CAMPAIGN_START = date(1996, 1, 2)


class IdentityEngineRunError(RuntimeError):
    """Raised when the unattended identity-engine run cannot be constructed safely."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--sec-user-agent",
        default=os.environ.get("SCOUT_SEC_USER_AGENT"),
        help=(
            "SEC-compliant requester identity including a contact email; alternatively set "
            "SCOUT_SEC_USER_AGENT"
        ),
    )
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    if not isinstance(args.sec_user_agent, str) or not args.sec_user_agent.strip():
        parser.error("--sec-user-agent or SCOUT_SEC_USER_AGENT is required")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()

    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable evidence is inconsistent; identity-engine run is blocked fail-closed"
            )

        profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
        candidate_path = (
            root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        )
        if not profile_path.is_file():
            raise IdentityEngineRunError("Tiingo profile is missing; run profile-tiingo first")
        if not candidate_path.is_file():
            raise IdentityEngineRunError("reviewed identity candidate is missing")

        profile = _load_profile(profile_path)
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
        reviewed = _fully_reviewed_query_symbols(candidate)
        pending = sorted(set(profile) - reviewed)

        queue_path = args.queue
        if queue_path is None:
            default_queue = (
                root
                / "evidence"
                / "identity-review-queue"
                / "tiingo-unreviewed-durable.json"
            )
            if default_queue.is_file():
                queue_path = default_queue
        if queue_path is not None:
            queued = _load_queue_symbols(queue_path)
            pending = [symbol for symbol in pending if symbol in queued]

        if args.limit is not None:
            pending = pending[: args.limit]

        output_root = root / "evidence" / "identity-engine"
        output_root.mkdir(parents=True, exist_ok=True)
        checkpoint_path = output_root / "sec-evidence-checkpoint.json"
        report_path = output_root / "identity-adjudication-report.json"
        ready_path = output_root / "ready-for-reviewed-seed.json"
        deferred_path = output_root / "deferred.json"

        checkpoint = {} if args.restart else _load_checkpoint(checkpoint_path)
        client = SecHttpClient(
            user_agent=args.sec_user_agent,
            minimum_interval_seconds=args.sleep,
        )
        catalog = load_sec_company_catalog(client)

        cases: list[tuple[IdentityReviewInput, IdentityEvidence]] = []
        for index, symbol in enumerate(pending, start=1):
            review = _review_input(profile[symbol])
            evidence = checkpoint.get(symbol)
            if evidence is None:
                print(
                    f"[{index}/{len(pending)}] collecting SEC identity evidence for {symbol}",
                    flush=True,
                )
                evidence = collect_sec_identity_evidence(
                    client=client,
                    catalog=catalog,
                    source_symbol=symbol,
                    observed_first_date=review.observed_first_date,
                    campaign_start=_CAMPAIGN_START,
                )
                checkpoint[symbol] = evidence
                _persist_checkpoint(checkpoint_path, checkpoint)
            else:
                print(
                    f"[{index}/{len(pending)}] reusing checkpointed SEC evidence for {symbol}",
                    flush=True,
                )
            cases.append((review, evidence))

        report = build_identity_batch_report(tuple(cases), campaign_start=_CAMPAIGN_START)
        persist_identity_batch_report(report_path, report)
        _persist_decision_subset(ready_path, report, ready=True)
        _persist_decision_subset(deferred_path, report, ready=False)
    except (
        IdentityEngineRunError,
        OperatorWorkspaceError,
        ReviewedIdentitySnapshotError,
        ValueError,
    ) as exc:
        print(f"Tiingo identity engine error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "profile_symbol_count": len(profile),
                "already_reviewed_symbol_count": len(reviewed),
                "attempted_symbol_count": len(pending),
                "ready_for_review_count": report.ready_count,
                "deferred_count": report.deferred_count,
                "checkpoint_path": str(checkpoint_path),
                "report_path": str(report_path),
                "ready_path": str(ready_path),
                "deferred_path": str(deferred_path),
                "tiingo_provider_calls_made": False,
                "sec_calls_made": True,
                "canonical_state_mutated": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _load_profile(path: Path) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityEngineRunError(f"cannot read Tiingo profile: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "tiingo-durable-profile-v0.1":
        raise IdentityEngineRunError("unsupported Tiingo durable profile")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        raise IdentityEngineRunError("Tiingo profile symbols must be an array")
    result: dict[str, dict[str, object]] = {}
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            raise IdentityEngineRunError("Tiingo profile symbol entry must be an object")
        symbol = _required_text(raw.get("source_symbol"), "source_symbol").upper()
        if symbol in result:
            raise IdentityEngineRunError(f"duplicate Tiingo profile symbol: {symbol}")
        result[symbol] = raw
    return result


def _review_input(raw: dict[str, object]) -> IdentityReviewInput:
    symbol = _required_text(raw.get("source_symbol"), "source_symbol").upper()
    first = _required_date(raw.get("first_date"), f"{symbol}.first_date")
    last = _required_date(raw.get("last_date"), f"{symbol}.last_date")
    anomalies = sum(
        _non_negative_int(raw.get(field), f"{symbol}.{field}") for field in _STRUCTURAL_COUNT_FIELDS
    )
    return IdentityReviewInput(
        source_symbol=symbol,
        observed_first_date=first,
        observed_last_date=last,
        row_count=_positive_int(raw.get("row_count"), f"{symbol}.row_count"),
        structural_anomaly_count=anomalies,
    )


def _fully_reviewed_query_symbols(candidate: object) -> set[str]:
    blocked = {gap.instrument_id for gap in candidate.coverage_gaps}
    return {
        link.query_symbol.upper()
        for link in candidate.provider_series_links
        if link.provider_id == "tiingo" and link.instrument_id not in blocked
    }


def _load_queue_symbols(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityEngineRunError(f"cannot read identity review queue: {path}") from exc
    if not isinstance(payload, dict):
        raise IdentityEngineRunError("identity review queue root must be an object")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        raise IdentityEngineRunError("identity review queue symbols must be an array")
    result: set[str] = set()
    for raw in raw_symbols:
        if isinstance(raw, str):
            symbol = raw
        elif isinstance(raw, dict):
            symbol = raw.get("source_symbol") or raw.get("symbol")
        else:
            raise IdentityEngineRunError("identity review queue contains malformed symbol entry")
        result.add(_required_text(symbol, "queue symbol").upper())
    return result


def _load_checkpoint(path: Path) -> dict[str, IdentityEvidence]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityEngineRunError(f"cannot read identity evidence checkpoint: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "sec-identity-checkpoint-v0.1":
        raise IdentityEngineRunError("unsupported identity evidence checkpoint")
    raw_items = payload.get("evidence")
    if not isinstance(raw_items, list):
        raise IdentityEngineRunError("identity evidence checkpoint entries must be an array")
    result: dict[str, IdentityEvidence] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise IdentityEngineRunError("identity evidence checkpoint entry must be an object")
        evidence = _evidence_from_payload(raw)
        result[evidence.source_symbol.upper()] = evidence
    return result


def _persist_checkpoint(path: Path, evidence_by_symbol: dict[str, IdentityEvidence]) -> None:
    payload = {
        "schema_version": "sec-identity-checkpoint-v0.1",
        "evidence": [
            _evidence_payload(evidence_by_symbol[symbol]) for symbol in sorted(evidence_by_symbol)
        ],
    }
    _atomic_json(path, payload)


def _persist_decision_subset(path: Path, report: object, *, ready: bool) -> None:
    decisions = [item for item in report.decisions if item.ready_for_review is ready]
    payload = {
        "schema_version": "identity-adjudication-subset-v0.1",
        "campaign_start": report.campaign_start.isoformat(),
        "decision_count": len(decisions),
        "decisions": [
            {
                "source_symbol": item.source_symbol,
                "state": item.state.value,
                "reason": item.reason,
                "observed_first_date": item.observed_first_date.isoformat(),
                "evidence": _evidence_payload(item.evidence),
            }
            for item in decisions
        ],
    }
    _atomic_json(path, payload)


def _evidence_payload(evidence: IdentityEvidence) -> dict[str, object]:
    payload = asdict(evidence)
    payload["state"] = evidence.state.value
    payload["effective_date"] = (
        evidence.effective_date.isoformat() if evidence.effective_date is not None else None
    )
    return payload


def _evidence_from_payload(raw: dict[str, object]) -> IdentityEvidence:
    try:
        state = IdentityEvidenceState(_required_text(raw.get("state"), "evidence.state"))
    except ValueError as exc:
        raise IdentityEngineRunError("identity evidence checkpoint has invalid state") from exc
    effective_raw = raw.get("effective_date")
    effective_date = None if effective_raw is None else _required_date(effective_raw, "effective_date")
    return IdentityEvidence(
        source_symbol=_required_text(raw.get("source_symbol"), "source_symbol"),
        state=state,
        source_url=_optional_text(raw.get("source_url")),
        source_title=_optional_text(raw.get("source_title")),
        effective_date=effective_date,
        regulator_id=_optional_text(raw.get("regulator_id")),
        company_name=_optional_text(raw.get("company_name")),
        exchange=_optional_text(raw.get("exchange")),
        detail=_required_text(raw.get("detail"), "detail"),
    )


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IdentityEngineRunError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise IdentityEngineRunError("optional identity evidence text must be non-empty when supplied")
    return value.strip()


def _required_date(value: object, field: str) -> date:
    text = _required_text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise IdentityEngineRunError(f"{field} must be an ISO date") from exc


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise IdentityEngineRunError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _non_negative_int(value, field)
    if result < 1:
        raise IdentityEngineRunError(f"{field} must be positive")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
