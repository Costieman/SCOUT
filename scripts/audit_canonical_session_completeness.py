"""Audit canonical daily bars against deterministic expected U.S. equity sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetNotFoundError,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.instrument_storage import (
    InstrumentMasterStorageError,
    InstrumentMasterStore,
)
from trade_scout.data.session_completeness import (
    SessionCompletenessError,
    audit_daily_bar_session_completeness,
    default_us_equity_session_calendar,
    persist_session_completeness_report,
)

_DEFAULT_DATASET_VERSION = DatasetVersion("tiingo-reviewed-split-only-v0.2")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--dataset-version",
        type=DatasetVersion,
        default=_DEFAULT_DATASET_VERSION,
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable evidence is inconsistent; session completeness audit is "
                "blocked fail-closed"
            )

        canonical_store = CanonicalDailyBarStore(workspace.canonical_root)
        manifest = canonical_store.get_manifest(args.dataset_version)
        if manifest is None:
            raise CanonicalDatasetNotFoundError(str(args.dataset_version))
        bars = canonical_store.load(args.dataset_version)
        identity = InstrumentMasterStore(workspace.canonical_root).load(
            manifest.universe_construction_version
        )
        calendar = default_us_equity_session_calendar()
        audit = audit_daily_bar_session_completeness(
            bars,
            instruments=identity.instruments,
            dataset_end_date=manifest.last_trade_date,
            calendar=calendar,
        )
        output = (
            workspace.root
            / "evidence"
            / "session-completeness"
            / f"{manifest.dataset_version}__{calendar.definition_version}.json"
        )
        persist_session_completeness_report(
            output,
            audit,
            source_canonical_content_sha256=manifest.content_checksum_sha256,
            identity_snapshot_version=manifest.universe_construction_version,
            calendar=calendar,
        )
    except (
        OperatorWorkspaceError,
        CanonicalDatasetNotFoundError,
        InstrumentMasterStorageError,
        SessionCompletenessError,
    ) as exc:
        print(f"canonical session completeness audit error: {exc}", file=sys.stderr)
        return 2

    incomplete = [item for item in audit.instruments if not item.complete]
    print(
        json.dumps(
            {
                "report_path": str(output),
                "dataset_version": str(audit.dataset_version),
                "source_canonical_content_sha256": manifest.content_checksum_sha256,
                "identity_snapshot_version": manifest.universe_construction_version,
                "calendar_definition_version": audit.calendar_definition_version,
                "dataset_end_date": audit.dataset_end_date.isoformat(),
                "instrument_count": audit.instrument_count,
                "complete_instrument_count": audit.complete_instrument_count,
                "missing_history_instrument_count": audit.missing_history_instrument_count,
                "expected_session_observation_count": audit.expected_session_observation_count,
                "missing_expected_session_count": audit.missing_expected_session_count,
                "unexpected_observed_date_count": audit.unexpected_observed_date_count,
                "duplicate_observed_date_count": audit.duplicate_observed_date_count,
                "complete": audit.complete,
                "incomplete_instruments": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "exchange": item.exchange,
                        "missing_history": item.missing_history,
                        "missing_expected_sessions": [
                            day.isoformat() for day in item.missing_expected_sessions
                        ],
                        "unexpected_observed_dates": [
                            day.isoformat() for day in item.unexpected_observed_dates
                        ],
                        "duplicate_observed_date_count": item.duplicate_observed_date_count,
                    }
                    for item in incomplete
                ],
                "provider_calls_made": False,
                "bars_fabricated": 0,
                "serving_selected": False,
                "provider_acceptance_changed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if audit.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
