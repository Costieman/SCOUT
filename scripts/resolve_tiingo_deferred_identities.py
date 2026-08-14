"""Re-check unresolved Tiingo identities and optionally promote newly proven cases.

Default mode is read-only with respect to canonical state: it writes only deferred-resolution
evidence/checkpoints. Pass --apply to materialize a new reviewed identity snapshot, register it,
promote its Tiingo prices, and select the resulting canonical dataset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

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
    load_sec_catalog,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.deferred_identity_resolution import (
    DeferredIdentityResolution,
    resolve_deferred_identity,
)
from trade_scout.data.instrument_storage import (
    InstrumentMasterIntegrityError,
    InstrumentMasterNotFoundError,
    InstrumentMasterPromotionRequest,
    InstrumentMasterStore,
)
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
    ReviewedIdentitySnapshotCandidate,
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
    persist_reviewed_identity_snapshot_candidate,
)


class DeferredResolutionRunError(RuntimeError):
    """Raised when deferred identity resolution cannot proceed safely."""


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
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Register/promote newly resolved identities after the evidence pass.",
    )
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
                "durable workspace verification failed; deferred resolution is blocked fail-closed"
            )

        profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
        candidate_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        deferred_path = root / "evidence" / "overnight-import" / "deferred.json"
        if not profile_path.is_file():
            raise DeferredResolutionRunError("Tiingo profile is missing")
        if not candidate_path.is_file():
            raise DeferredResolutionRunError("reviewed identity candidate is missing")
        if not deferred_path.is_file():
            raise DeferredResolutionRunError("overnight deferred identity evidence is missing")

        profile_symbols = _load_profile_symbols(profile_path)
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
        reviewed_symbols = {
            link.query_symbol.upper()
            for link in candidate.provider_series_links
            if link.provider_id == "tiingo"
        }
        unresolved_symbols = profile_symbols - reviewed_symbols
        original_deferred = _load_evidence_list(deferred_path)
        deferred_by_symbol = {item.source_symbol: item for item in original_deferred}

        # Symbols that were already deferred by dedicated/manual lineage work are deliberately not
        # passed through this bulk rule. This protects known mergers, predecessor/successor cases,
        # when-issued boundaries, and other adjudications from accidental auto-approval.
        protected_symbols = frozenset(unresolved_symbols - set(deferred_by_symbol))
        eligible_symbols = sorted(unresolved_symbols & set(deferred_by_symbol))
        if args.limit is not None:
            eligible_symbols = eligible_symbols[: args.limit]

        output_root = root / "evidence" / "deferred-resolution"
        output_root.mkdir(parents=True, exist_ok=True)
        checkpoint_path = output_root / "checkpoint.json"
        ready_path = output_root / "ready.json"
        remaining_path = output_root / "remaining.json"
        summary_path = output_root / "summary.json"
        staged_candidate_path = (
            root / "evidence" / "instrument-identity" / "tiingo-deferred-resolved-candidate.json"
        )

        checkpoint = {} if args.restart else _load_resolution_checkpoint(checkpoint_path)
        client = SecIdentityClient(
            user_agent=args.sec_user_agent,
            minimum_interval_seconds=args.sleep,
        )
        catalog = load_sec_catalog(client)

        for index, symbol in enumerate(eligible_symbols, start=1):
            if symbol in checkpoint:
                print(f"[{index}/{len(eligible_symbols)}] {symbol}: checkpoint", flush=True)
                continue
            print(f"[{index}/{len(eligible_symbols)}] {symbol}: resolving boundary", flush=True)
            resolution = resolve_deferred_identity(
                client=client,
                catalog=catalog,
                evidence=deferred_by_symbol[symbol],
                protected_symbols=protected_symbols,
            )
            checkpoint[symbol] = resolution
            _persist_resolution_checkpoint(checkpoint_path, checkpoint)
            print(
                f"    -> {resolution.status} {resolution.resolution_kind}",
                flush=True,
            )

        decisions = tuple(
            checkpoint[symbol] for symbol in eligible_symbols if symbol in checkpoint
        )
        ready_resolutions = tuple(item for item in decisions if item.ready)
        remaining = tuple(item for item in decisions if not item.ready)
        _write_resolution_list(ready_path, ready_resolutions)
        _write_resolution_list(remaining_path, remaining)

        base_summary: dict[str, object] = {
            "status": "CHECK_COMPLETE",
            "profile_symbol_count": len(profile_symbols),
            "current_reviewed_symbol_count": len(reviewed_symbols),
            "unresolved_symbol_count": len(unresolved_symbols),
            "bulk_deferred_symbol_count": len(original_deferred),
            "protected_legacy_symbol_count": len(protected_symbols),
            "protected_legacy_symbols": sorted(protected_symbols),
            "attempted_symbol_count": len(eligible_symbols),
            "new_ready_count": len(ready_resolutions),
            "remaining_deferred_count": len(remaining),
            "ready_resolution_kind_counts": _counts(
                item.resolution_kind for item in ready_resolutions
            ),
            "remaining_resolution_kind_counts": _counts(
                item.resolution_kind for item in remaining
            ),
            "checkpoint_path": str(checkpoint_path),
            "ready_path": str(ready_path),
            "remaining_path": str(remaining_path),
            "canonical_state_mutated": False,
            "sec_calls_made": True,
            "tiingo_provider_calls_made": False,
        }

        if not args.apply:
            _atomic_json(summary_path, base_summary)
            print(json.dumps(base_summary, indent=2, sort_keys=True))
            return 0

        if not ready_resolutions:
            base_summary["status"] = "COMPLETE_NO_NEW_READY"
            _atomic_json(summary_path, base_summary)
            print(json.dumps(base_summary, indent=2, sort_keys=True))
            return 0

        ready_evidence = tuple(item.as_ready_evidence() for item in ready_resolutions)
        generated_candidate = build_auto_reviewed_candidate(
            existing=candidate,
            ready_evidence=ready_evidence,
        )
        _validate_generated_candidate(candidate, generated_candidate, ready_evidence)
        persist_reviewed_identity_snapshot_candidate(staged_candidate_path, generated_candidate)
        reloaded = load_reviewed_identity_snapshot_candidate(staged_candidate_path)
        if reloaded != generated_candidate:
            raise DeferredResolutionRunError(
                "staged deferred-resolution candidate failed exact persistence/reload check"
            )

        _register_identity_snapshot(workspace.canonical_root, generated_candidate)

        dataset_version_text = candidate_dataset_version(generated_candidate)
        dataset_version = DatasetVersion(dataset_version_text)
        campaign_plan = load_tiingo_sp500_campaign_plan(
            repository_root / "configs" / "tiingo_sp500_campaign_v0.1.json"
        )
        promotion = promote_reviewed_tiingo_prices(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
            candidate_path=staged_candidate_path,
            canonical_root=workspace.canonical_root,
            dataset_version=dataset_version,
            dataset_start_date=campaign_plan.history_start,
            dataset_end_date=campaign_plan.history_end,
        )
        promotion_report_path = (
            root / "evidence" / "canonical-promotion" / f"{dataset_version_text}.json"
        )
        persist_tiingo_canonical_promotion_report(promotion_report_path, promotion)

        # Move the standard identity pointer only after all newly included prices promote cleanly.
        persist_reviewed_identity_snapshot_candidate(candidate_path, generated_candidate)

        selected = False
        if not args.no_select:
            refreshed_workspace = load_operator_workspace(root)
            configure_operator_workspace(
                refreshed_workspace,
                canonical_dataset_version=dataset_version_text,
                scanner_required_session=refreshed_workspace.manifest.scanner_required_session,
            )
            selected = True

        base_summary.update(
            {
                "status": "COMPLETE",
                "canonical_state_mutated": True,
                "new_identity_snapshot_version": generated_candidate.snapshot_version,
                "new_reviewed_symbol_count": len(generated_candidate.provider_series_links),
                "canonical_dataset_version": dataset_version_text,
                "canonical_dataset_selected": selected,
                "promoted_symbol_count": promotion.symbol_count,
                "promoted_record_count": promotion.row_count,
                "staged_candidate_path": str(staged_candidate_path),
                "promotion_report_path": str(promotion_report_path),
            }
        )
        _atomic_json(summary_path, base_summary)
        print(json.dumps(base_summary, indent=2, sort_keys=True))
        return 0
    except (
        AutoIdentityImportError,
        DeferredResolutionRunError,
        InstrumentMasterIntegrityError,
        OperatorWorkspaceError,
        ReviewedIdentitySnapshotError,
        TiingoCanonicalPromotionError,
        TiingoSp500CampaignError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"deferred Tiingo identity resolution error: {exc}", file=sys.stderr)
        return 2


def _validate_generated_candidate(
    existing: ReviewedIdentitySnapshotCandidate,
    generated: ReviewedIdentitySnapshotCandidate,
    ready: tuple[AutoIdentityEvidence, ...],
) -> None:
    expected_new = {item.source_symbol for item in ready}
    existing_queries = {
        link.query_symbol.upper()
        for link in existing.provider_series_links
        if link.provider_id == "tiingo"
    }
    generated_queries = {
        link.query_symbol.upper()
        for link in generated.provider_series_links
        if link.provider_id == "tiingo"
    }
    if generated_queries - existing_queries != expected_new:
        raise DeferredResolutionRunError(
            "generated candidate does not contain exactly the newly resolved provider symbols"
        )
    instrument_ids = [str(item.instrument_id) for item in generated.instruments]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise DeferredResolutionRunError(
            "generated candidate contains duplicate permanent instrument IDs; security identity seed is unsafe"
        )
    if not generated.promotion_ready:
        raise DeferredResolutionRunError("generated candidate is not promotion-ready")


def _register_identity_snapshot(
    canonical_root: Path,
    candidate: ReviewedIdentitySnapshotCandidate,
) -> None:
    store = InstrumentMasterStore(canonical_root)
    source_batch_ids = (
        f"deferred-identity-seed-sha256:{candidate.identity_seed_sha256}",
        f"deferred-lineage-audit-sha256:{candidate.lineage_audit_sha256}",
    )
    try:
        store.get_manifest(candidate.snapshot_version)
    except InstrumentMasterNotFoundError:
        store.promote(
            candidate.instruments,
            candidate.symbol_history,
            InstrumentMasterPromotionRequest(
                snapshot_version=candidate.snapshot_version,
                primary_provider_id=candidate.primary_provider_id,
                created_at=datetime.now(UTC),
                source_batch_ids=source_batch_ids,
                identity_definition_version=candidate.identity_definition_version,
                symbol_history_definition_version=candidate.symbol_history_definition_version,
            ),
        )
    loaded = store.load(candidate.snapshot_version)
    if loaded.instruments != candidate.instruments or loaded.symbol_history != candidate.symbol_history:
        raise DeferredResolutionRunError(
            "registered instrument master does not exactly match deferred-resolution candidate"
        )


def _load_profile_symbols(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise DeferredResolutionRunError("Tiingo profile has unsupported structure")
    result: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise DeferredResolutionRunError("Tiingo profile contains malformed symbol row")
        result.add(_text(row.get("source_symbol"), "profile source_symbol").upper())
    return result


def _load_evidence_list(path: Path) -> tuple[AutoIdentityEvidence, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("evidence") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise DeferredResolutionRunError("auto-identity evidence list has unsupported structure")
    result: list[AutoIdentityEvidence] = []
    for row in rows:
        if not isinstance(row, dict):
            raise DeferredResolutionRunError("auto-identity evidence list contains malformed row")
        result.append(
            AutoIdentityEvidence(
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
        )
    return tuple(result)


def _load_resolution_checkpoint(path: Path) -> dict[str, DeferredIdentityResolution]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "deferred-identity-resolution-checkpoint-v0.1":
        raise DeferredResolutionRunError("unsupported deferred-resolution checkpoint")
    rows = payload.get("resolutions")
    if not isinstance(rows, list):
        raise DeferredResolutionRunError("deferred-resolution checkpoint rows must be an array")
    result: dict[str, DeferredIdentityResolution] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise DeferredResolutionRunError("malformed deferred-resolution checkpoint row")
        item = _resolution_from_payload(row)
        result[item.source_symbol] = item
    return result


def _persist_resolution_checkpoint(
    path: Path,
    checkpoint: dict[str, DeferredIdentityResolution],
) -> None:
    _atomic_json(
        path,
        {
            "schema_version": "deferred-identity-resolution-checkpoint-v0.1",
            "resolutions": [
                _resolution_payload(checkpoint[symbol]) for symbol in sorted(checkpoint)
            ],
        },
    )


def _write_resolution_list(
    path: Path,
    rows: tuple[DeferredIdentityResolution, ...],
) -> None:
    _atomic_json(
        path,
        {
            "schema_version": "deferred-identity-resolution-list-v0.1",
            "count": len(rows),
            "resolutions": [_resolution_payload(item) for item in rows],
        },
    )


def _resolution_payload(item: DeferredIdentityResolution) -> dict[str, object]:
    payload = asdict(item)
    payload["observed_first_date"] = item.observed_first_date.isoformat()
    return payload


def _resolution_from_payload(row: dict[str, object]) -> DeferredIdentityResolution:
    return DeferredIdentityResolution(
        source_symbol=_text(row.get("source_symbol"), "source_symbol").upper(),
        observed_first_date=_iso_date(row.get("observed_first_date"), "observed_first_date"),
        original_evidence_kind=_text(row.get("original_evidence_kind"), "original_evidence_kind"),
        original_reason=_text(row.get("original_reason"), "original_reason"),
        status=_text(row.get("status"), "status"),
        resolution_kind=_text(row.get("resolution_kind"), "resolution_kind"),
        cik=_optional_int(row.get("cik")),
        company_name=_optional_text(row.get("company_name")),
        exchange=_optional_text(row.get("exchange")),
        evidence_url=_optional_text(row.get("evidence_url")),
        evidence_title=_optional_text(row.get("evidence_title")),
        reason=_text(row.get("reason"), "reason"),
    )


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        text = str(value)
        result[text] = result.get(text, 0) + 1
    return dict(sorted(result.items()))


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeferredResolutionRunError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _iso_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError as exc:
        raise DeferredResolutionRunError(f"{field} must be an ISO date") from exc


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DeferredResolutionRunError("optional integer must be a non-negative integer")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise DeferredResolutionRunError(f"{field} must be boolean")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
