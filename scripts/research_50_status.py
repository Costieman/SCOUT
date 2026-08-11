"""Report acquisition, identity-review, and canonical readiness for the 50-stock research target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.app.operator_workspace import (
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.tiingo_campaign_state import load_tiingo_safe_campaign_state
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--target-config",
        type=Path,
        default=Path("configs/tiingo_research_50_targets_v0.1.json"),
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise SystemExit("durable workspace evidence is inconsistent; expansion status is blocked")

    config_path = args.target_config
    if not config_path.is_absolute():
        config_path = repository_root / config_path
    target_symbols = _target_symbols(config_path)

    completed: set[str] = set()
    if workspace.tiingo_safe_state_path.is_file():
        state = load_tiingo_safe_campaign_state(workspace.tiingo_safe_state_path)
        completed = set(state.durable_completed_symbols)

    candidate_path = (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    reviewed: set[str] = set()
    candidate = None
    if candidate_path.is_file():
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
        blocked = {item.instrument_id for item in candidate.coverage_gaps}
        reviewed = {
            item.query_symbol
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and item.instrument_id not in blocked
        }

    canonical: set[str] = set()
    selected_version = workspace.manifest.canonical_dataset_version
    if selected_version is not None and candidate is not None:
        bars = CanonicalDailyBarStore(workspace.canonical_root).load(
            DatasetVersion(selected_version)
        )
        instrument_ids = {bar.instrument_id for bar in bars}
        canonical = {
            item.query_symbol
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and item.instrument_id in instrument_ids
        }

    payload = {
        "target_version": "reviewed-research-50-v0.1",
        "target_count": len(target_symbols),
        "acquired_target_count": len(target_symbols & completed),
        "reviewed_target_count": len(target_symbols & reviewed),
        "selected_canonical_target_count": len(target_symbols & canonical),
        "selected_canonical_dataset_version": selected_version,
        "missing_acquisition": sorted(target_symbols - completed),
        "missing_review": sorted(target_symbols - reviewed),
        "missing_selected_canonical": sorted(target_symbols - canonical),
        "ready_for_50_stock_research": len(target_symbols & canonical) == len(target_symbols),
        "point_in_time_sp500_claim": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _target_symbols(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"cannot read research target config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit("research target config is invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "tiingo-research-targets-v0.1":
        raise SystemExit("unsupported research target config")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list) or not all(isinstance(item, str) for item in raw_symbols):
        raise SystemExit("research target symbols are invalid")
    symbols = {item.strip().upper() for item in raw_symbols if item.strip()}
    if len(symbols) != payload.get("target_count"):
        raise SystemExit("research target count does not match unique symbols")
    return symbols


if __name__ == "__main__":
    raise SystemExit(main())
