"""Print metadata-only profile evidence for acquired research targets awaiting identity review."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from trade_scout.app.operator_workspace import (
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.providers.tiingo_campaign_state import load_tiingo_safe_campaign_state
from trade_scout.data.providers.tiingo_review_probe import build_tiingo_review_probe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise SystemExit("durable workspace evidence is inconsistent; identity probe is blocked")

    state = load_tiingo_safe_campaign_state(workspace.tiingo_safe_state_path)
    target_path = repository_root / "configs" / "tiingo_research_50_targets_v0.1.json"
    target_symbols = _target_symbols(target_path)
    profile_path = workspace.root / "evidence" / "tiingo-profile" / "profile.json"
    candidate_path = (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    rows = build_tiingo_review_probe(
        profile_path=profile_path,
        candidate_path=candidate_path,
        target_symbols=target_symbols,
        acquired_symbols=set(state.durable_completed_symbols),
    )
    payload = {
        "schema_version": "tiingo-research-50-review-probe-v0.1",
        "pending_review_count": len(rows),
        "all_pending_structurally_clean": all(
            item.structural_anomaly_count == 0 for item in rows
        ),
        "symbols": [asdict(item) for item in rows],
        "provider_calls_made": False,
        "identity_promotion_performed": False,
        "price_promotion_performed": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _target_symbols(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read research target config: {path}") from exc
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
