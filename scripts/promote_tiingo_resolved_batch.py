"""Combine independently proven Tiingo identity evidence and promote one canonical batch.

Default mode is a fail-closed preflight that builds and persists a staged candidate but does not
register identity or mutate canonical state. Pass --apply only after the preflight summary is clean.
No provider or SEC calls are made by this script; it consumes already checkpointed evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
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
    build_auto_reviewed_candidate,
    candidate_dataset_version,
)
from trade_scout.data.contracts import DatasetVersion
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
from trade_scout.data.resolved_identity_batch import (
    ResolvedIdentityBatchError,
    load_resolved_identity_batch,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotCandidate,
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
    persist_reviewed_identity_snapshot_candidate,
)


class ResolvedBatchPromotionError(RuntimeError):
    """Raised when the resolved evidence batch cannot be promoted safely."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Register identity, promote prices, advance identity pointer, and select dataset.",
    )
    parser.add_argument("--no-select", action="store_true")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()

    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable workspace verification failed; resolved batch promotion is blocked"
            )

        candidate_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        deferred_ready_path = root / "evidence" / "deferred-resolution" / "ready.json"
        deferred_remaining_path = root / "evidence" / "deferred-resolution" / "remaining.json"
        historical_ready_path = (
            root / "evidence" / "deferred-resolution" / "historical-index" / "ready.json"
        )
        output_root = root / "evidence" / "resolved-batch-promotion"
        output_root.mkdir(parents=True, exist_ok=True)
        staged_candidate_path = (
            root / "evidence" / "instrument-identity" / "tiingo-resolved-batch-candidate.json"
        )
        summary_path = output_root / "summary.json"

        existing = load_reviewed_identity_snapshot_candidate(candidate_path)
        batch = load_resolved_identity_batch(
            deferred_ready_path=deferred_ready_path,
            deferred_remaining_path=deferred_remaining_path,
            historical_ready_path=historical_ready_path,
        )
        if not batch.evidence:
            raise ResolvedBatchPromotionError("resolved evidence batch is empty")

        generated = build_auto_reviewed_candidate(existing=existing, ready_evidence=batch.evidence)
        _validate_generated_candidate(existing, generated, batch.evidence)
        persist_reviewed_identity_snapshot_candidate(staged_candidate_path, generated)
        reloaded = load_reviewed_identity_snapshot_candidate(staged_candidate_path)
        if reloaded != generated:
            raise ResolvedBatchPromotionError(
                "staged resolved-batch candidate failed exact persistence/reload verification"
            )

        existing_symbols = _tiingo_symbols(existing)
        generated_symbols = _tiingo_symbols(generated)
        new_symbols = sorted(generated_symbols - existing_symbols)
        dataset_version_text = candidate_dataset_version(generated)

        summary: dict[str, object] = {
            "status": "PREFLIGHT_PASS",
            "canonical_state_mutated": False,
            "provider_calls_made": False,
            "sec_calls_made": False,
            "existing_reviewed_symbol_count": len(existing_symbols),
            "deferred_resolver_ready_count": batch.deferred_resolver_count,
            "historical_index_ready_count": batch.historical_index_count,
            "resolved_batch_count": len(batch.evidence),
            "new_symbols": new_symbols,
            "new_identity_snapshot_version": generated.snapshot_version,
            "target_reviewed_symbol_count": len(generated_symbols),
            "target_canonical_dataset_version": dataset_version_text,
            "staged_candidate_path": str(staged_candidate_path),
        }

        if not args.apply:
            _atomic_json(summary_path, summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        _register_identity_snapshot(workspace.canonical_root, generated)
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
        if promotion.symbol_count != len(generated_symbols):
            raise ResolvedBatchPromotionError(
                "canonical promotion symbol count does not equal generated reviewed scope"
            )
        promotion_report_path = (
            root / "evidence" / "canonical-promotion" / f"{dataset_version_text}.json"
        )
        persist_tiingo_canonical_promotion_report(promotion_report_path, promotion)

        # Advance the standard reviewed candidate only after canonical promotion succeeds.
        persist_reviewed_identity_snapshot_candidate(candidate_path, generated)
        selected = False
        if not args.no_select:
            refreshed = load_operator_workspace(root)
            configure_operator_workspace(
                refreshed,
                canonical_dataset_version=dataset_version_text,
                scanner_required_session=refreshed.manifest.scanner_required_session,
            )
            selected = True

        summary.update(
            {
                "status": "COMPLETE",
                "canonical_state_mutated": True,
                "canonical_dataset_selected": selected,
                "canonical_dataset_version": dataset_version_text,
                "promoted_symbol_count": promotion.symbol_count,
                "promoted_record_count": promotion.row_count,
                "promotion_report_path": str(promotion_report_path),
            }
        )
        _atomic_json(summary_path, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (
        AutoIdentityImportError,
        InstrumentMasterIntegrityError,
        OperatorWorkspaceError,
        ResolvedBatchPromotionError,
        ResolvedIdentityBatchError,
        ReviewedIdentitySnapshotError,
        TiingoCanonicalPromotionError,
        TiingoSp500CampaignError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"resolved Tiingo batch promotion error: {exc}", file=sys.stderr)
        return 2


def _validate_generated_candidate(
    existing: ReviewedIdentitySnapshotCandidate,
    generated: ReviewedIdentitySnapshotCandidate,
    ready: tuple[AutoIdentityEvidence, ...],
) -> None:
    expected_new = {item.source_symbol.upper() for item in ready}
    existing_queries = _tiingo_symbols(existing)
    generated_queries = _tiingo_symbols(generated)
    actual_new = generated_queries - existing_queries
    if actual_new != expected_new:
        missing = sorted(expected_new - actual_new)
        unexpected = sorted(actual_new - expected_new)
        raise ResolvedBatchPromotionError(
            f"generated candidate new-symbol mismatch; missing={missing}, unexpected={unexpected}"
        )
    if existing_queries.intersection(expected_new):
        raise ResolvedBatchPromotionError("resolved batch contains an already reviewed symbol")
    instrument_ids = [str(item.instrument_id) for item in generated.instruments]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise ResolvedBatchPromotionError("generated candidate contains duplicate instrument IDs")
    query_symbols = [
        item.query_symbol.upper()
        for item in generated.provider_series_links
        if item.provider_id == "tiingo"
    ]
    if len(query_symbols) != len(set(query_symbols)):
        raise ResolvedBatchPromotionError("generated candidate contains duplicate Tiingo symbols")
    if not generated.promotion_ready or generated.coverage_gaps:
        raise ResolvedBatchPromotionError("generated candidate is not promotion-ready")


def _register_identity_snapshot(
    canonical_root: Path,
    candidate: ReviewedIdentitySnapshotCandidate,
) -> None:
    store = InstrumentMasterStore(canonical_root)
    source_batch_ids = (
        f"resolved-batch-identity-seed-sha256:{candidate.identity_seed_sha256}",
        f"resolved-batch-lineage-audit-sha256:{candidate.lineage_audit_sha256}",
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
        raise ResolvedBatchPromotionError(
            "registered instrument master does not exactly match resolved-batch candidate"
        )


def _tiingo_symbols(candidate: ReviewedIdentitySnapshotCandidate) -> set[str]:
    return {
        link.query_symbol.upper()
        for link in candidate.provider_series_links
        if link.provider_id == "tiingo"
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
