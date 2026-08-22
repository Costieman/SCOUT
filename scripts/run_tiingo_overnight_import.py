"""Run fail-closed automatic identity triage and canonical Tiingo promotion overnight."""

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
    configure_operator_workspace,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.auto_identity_import import (
    AutoIdentityEvidence,
    AutoIdentityImportError,
    SecIdentityClient,
    build_auto_reviewed_candidate,
    candidate_dataset_version,
    collect_auto_identity_evidence,
    load_sec_catalog,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.tiingo_canonical_promotion import (
    TiingoCanonicalPromotionError,
    persist_tiingo_canonical_promotion_report,
    promote_reviewed_tiingo_prices,
)
from trade_scout.data.providers.tiingo_sp500_campaign import (
    TiingoSp500CampaignError,
    load_tiingo_sp500_campaign_plan,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
    persist_reviewed_identity_snapshot_candidate,
)

_CAMPAIGN_START = date(1996, 1, 2)
_STRUCTURAL_FIELDS = (
    "invalid_date_row_count",
    "duplicate_date_count",
    "non_monotonic_date_count",
    "missing_required_field_row_count",
    "invalid_numeric_row_count",
    "ohlc_invariant_violation_count",
    "negative_volume_count",
    "long_calendar_gap_count",
)


class OvernightImportError(RuntimeError):
    """Raised when the overnight import cannot advance safely."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--sec-user-agent",
        default=os.environ.get("SCOUT_SEC_USER_AGENT"),
        help="Requester identity including contact email; may use SCOUT_SEC_USER_AGENT.",
    )
    parser.add_argument("--sleep", type=float, default=0.6)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--no-select", action="store_true")
    args = parser.parse_args()

    if not isinstance(args.sec_user_agent, str) or "@" not in args.sec_user_agent:
        parser.error("--sec-user-agent or SCOUT_SEC_USER_AGENT with a contact email is required")
    if args.sleep < 0:
        parser.error("--sleep must be non-negative")
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
                "durable workspace verification failed; overnight import is blocked fail-closed"
            )

        profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
        current_candidate_path = (
            root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        )
        if not profile_path.is_file():
            raise OvernightImportError("Tiingo profile is missing; run profile-tiingo first")
        if not current_candidate_path.is_file():
            raise OvernightImportError("current reviewed identity candidate is missing")

        profile = _load_profile(profile_path)
        existing_candidate = load_reviewed_identity_snapshot_candidate(current_candidate_path)
        if not existing_candidate.promotion_ready:
            raise OvernightImportError(
                "current reviewed candidate contains coverage gaps; automatic expansion is blocked"
            )

        already_reviewed = {
            link.query_symbol.upper()
            for link in existing_candidate.provider_series_links
            if link.provider_id == "tiingo"
        }
        pending = sorted(set(profile) - already_reviewed)
        queue_path = root / "evidence" / "identity-review-queue" / "tiingo-unreviewed-durable.json"
        if queue_path.is_file():
            queued = _load_queue_symbols(queue_path)
            pending = [symbol for symbol in pending if symbol in queued]
        if args.limit is not None:
            pending = pending[: args.limit]

        evidence_root = root / "evidence" / "overnight-import"
        evidence_root.mkdir(parents=True, exist_ok=True)
        checkpoint_path = evidence_root / "identity-checkpoint.json"
        ready_path = evidence_root / "ready.json"
        deferred_path = evidence_root / "deferred.json"
        summary_path = evidence_root / "summary.json"
        generated_candidate_path = (
            root / "evidence" / "instrument-identity" / "tiingo-auto-reviewed-candidate.json"
        )

        checkpoint = {} if args.restart else _load_checkpoint(checkpoint_path)
        client = SecIdentityClient(
            user_agent=args.sec_user_agent,
            minimum_interval_seconds=args.sleep,
        )
        catalog = load_sec_catalog(client)

        for index, symbol in enumerate(pending, start=1):
            if symbol in checkpoint:
                print(f"[{index}/{len(pending)}] {symbol}: checkpoint", flush=True)
                continue
            row = profile[symbol]
            print(f"[{index}/{len(pending)}] {symbol}: SEC evidence", flush=True)
            evidence = collect_auto_identity_evidence(
                client=client,
                catalog=catalog,
                source_symbol=symbol,
                observed_first_date=_iso_date(row.get("first_date"), f"{symbol}.first_date"),
                structural_anomaly_count=sum(
                    _non_negative_int(row.get(field), f"{symbol}.{field}")
                    for field in _STRUCTURAL_FIELDS
                ),
                campaign_start=_CAMPAIGN_START,
            )
            checkpoint[symbol] = evidence
            _persist_checkpoint(checkpoint_path, checkpoint)

        decisions = tuple(checkpoint[symbol] for symbol in pending if symbol in checkpoint)
        ready = tuple(item for item in decisions if item.ready)
        deferred = tuple(item for item in decisions if not item.ready)
        _write_evidence_list(ready_path, ready)
        _write_evidence_list(deferred_path, deferred)

        if not ready:
            summary = {
                "status": "COMPLETE_NO_NEW_READY",
                "profile_symbol_count": len(profile),
                "already_reviewed_symbol_count": len(already_reviewed),
                "attempted_symbol_count": len(pending),
                "new_ready_count": 0,
                "deferred_count": len(deferred),
                "canonical_promoted": False,
                "tiingo_provider_calls_made": False,
                "sec_calls_made": True,
            }
            _atomic_json(summary_path, summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        generated_candidate = build_auto_reviewed_candidate(
            existing=existing_candidate,
            ready_evidence=ready,
        )
        if not generated_candidate.promotion_ready:
            raise OvernightImportError("generated candidate is not promotion-ready")
        persist_reviewed_identity_snapshot_candidate(
            generated_candidate_path,
            generated_candidate,
        )
        reloaded = load_reviewed_identity_snapshot_candidate(generated_candidate_path)
        if reloaded != generated_candidate:
            raise OvernightImportError("generated candidate failed exact persistence/reload check")

        dataset_version_text = candidate_dataset_version(generated_candidate)
        dataset_version = DatasetVersion(dataset_version_text)
        campaign_plan = load_tiingo_sp500_campaign_plan(
            repository_root / "configs" / "tiingo_sp500_campaign_v0.1.json"
        )
        promotion = promote_reviewed_tiingo_prices(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
            candidate_path=generated_candidate_path,
            canonical_root=workspace.canonical_root,
            dataset_version=dataset_version,
            dataset_start_date=campaign_plan.history_start,
            dataset_end_date=campaign_plan.history_end,
        )
        promotion_report_path = (
            root / "evidence" / "canonical-promotion" / f"{dataset_version_text}.json"
        )
        persist_tiingo_canonical_promotion_report(promotion_report_path, promotion)

        # The standard candidate pointer moves only after canonical promotion succeeds.
        persist_reviewed_identity_snapshot_candidate(
            current_candidate_path,
            generated_candidate,
        )

        selected = False
        if not args.no_select:
            refreshed_workspace = load_operator_workspace(root)
            configure_operator_workspace(
                refreshed_workspace,
                canonical_dataset_version=dataset_version_text,
                scanner_required_session=refreshed_workspace.manifest.scanner_required_session,
            )
            selected = True

        summary = {
            "status": "COMPLETE",
            "profile_symbol_count": len(profile),
            "previous_reviewed_symbol_count": len(already_reviewed),
            "attempted_symbol_count": len(pending),
            "new_ready_count": len(ready),
            "deferred_count": len(deferred),
            "promoted_symbol_count": promotion.symbol_count,
            "promoted_record_count": promotion.row_count,
            "canonical_dataset_version": dataset_version_text,
            "canonical_dataset_selected": selected,
            "identity_snapshot_version": generated_candidate.snapshot_version,
            "candidate_path": str(current_candidate_path),
            "generated_candidate_path": str(generated_candidate_path),
            "promotion_report_path": str(promotion_report_path),
            "ready_path": str(ready_path),
            "deferred_path": str(deferred_path),
            "checkpoint_path": str(checkpoint_path),
            "tiingo_provider_calls_made": False,
            "sec_calls_made": True,
        }
        _atomic_json(summary_path, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (
        AutoIdentityImportError,
        OvernightImportError,
        OperatorWorkspaceError,
        ReviewedIdentitySnapshotError,
        TiingoCanonicalPromotionError,
        TiingoSp500CampaignError,
        ValueError,
    ) as exc:
        print(f"overnight Tiingo import error: {exc}", file=sys.stderr)
        return 2


def _load_profile(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OvernightImportError("Tiingo profile root must be an object")
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise OvernightImportError("Tiingo profile symbols must be an array")
    result: dict[str, dict[str, object]] = {}
    for row in symbols:
        if not isinstance(row, dict):
            raise OvernightImportError("Tiingo profile symbol row must be an object")
        symbol = _text(row.get("source_symbol"), "source_symbol").upper()
        if symbol in result:
            raise OvernightImportError(f"duplicate profile symbol: {symbol}")
        result[symbol] = row
    return result


def _load_queue_symbols(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise OvernightImportError("identity queue has unsupported structure")
    result: set[str] = set()
    for row in payload["symbols"]:
        if isinstance(row, str):
            value = row
        elif isinstance(row, dict):
            value = row.get("source_symbol") or row.get("symbol")
        else:
            raise OvernightImportError("identity queue contains malformed row")
        result.add(_text(value, "queue symbol").upper())
    return result


def _load_checkpoint(path: Path) -> dict[str, AutoIdentityEvidence]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "auto-identity-checkpoint-v0.1"
    ):
        raise OvernightImportError("unsupported overnight identity checkpoint")
    rows = payload.get("evidence")
    if not isinstance(rows, list):
        raise OvernightImportError("overnight identity checkpoint evidence must be an array")
    result: dict[str, AutoIdentityEvidence] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise OvernightImportError("malformed overnight identity checkpoint row")
        evidence = _evidence_from_payload(row)
        result[evidence.source_symbol] = evidence
    return result


def _persist_checkpoint(path: Path, checkpoint: dict[str, AutoIdentityEvidence]) -> None:
    _atomic_json(
        path,
        {
            "schema_version": "auto-identity-checkpoint-v0.1",
            "evidence": [_evidence_payload(checkpoint[symbol]) for symbol in sorted(checkpoint)],
        },
    )


def _write_evidence_list(path: Path, evidence: tuple[AutoIdentityEvidence, ...]) -> None:
    _atomic_json(
        path,
        {
            "schema_version": "auto-identity-evidence-list-v0.1",
            "count": len(evidence),
            "evidence": [_evidence_payload(item) for item in evidence],
        },
    )


def _evidence_payload(item: AutoIdentityEvidence) -> dict[str, object]:
    payload = asdict(item)
    payload["observed_first_date"] = item.observed_first_date.isoformat()
    return payload


def _evidence_from_payload(row: dict[str, object]) -> AutoIdentityEvidence:
    return AutoIdentityEvidence(
        source_symbol=_text(row.get("source_symbol"), "source_symbol").upper(),
        observed_first_date=_iso_date(row.get("observed_first_date"), "observed_first_date"),
        cik=_optional_int(row.get("cik")),
        company_name=_optional_text(row.get("company_name")),
        exchange=_optional_text(row.get("exchange")),
        source_url=_optional_text(row.get("source_url")),
        source_title=_optional_text(row.get("source_title")),
        evidence_kind=_text(row.get("evidence_kind"), "evidence_kind"),
        ready=_boolean(row.get("ready"), "ready"),
        reason=_text(row.get("reason"), "reason"),
    )


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OvernightImportError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _iso_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError as exc:
        raise OvernightImportError(f"{field} must be an ISO date") from exc


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OvernightImportError(f"{field} must be a non-negative integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, "optional integer")


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise OvernightImportError(f"{field} must be boolean")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
