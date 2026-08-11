"""Acquire the next bounded slice of the 50-stock exploratory research target."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from trade_scout.app.operator_workspace import (
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--max-symbols", type=int, default=5)
    args = parser.parse_args()
    if args.max_symbols < 1:
        raise SystemExit("--max-symbols must be positive")

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise SystemExit("durable workspace evidence is inconsistent; acquisition is blocked")

    runner = repository_root / "scripts" / "run_tiingo_sp500_durable_slice.py"
    plan = repository_root / "configs" / "tiingo_sp500_campaign_v0.1.json"
    target = repository_root / "configs" / "tiingo_research_50_targets_v0.1.json"
    command = [
        sys.executable,
        str(runner),
        "--plan",
        str(plan),
        "--durable-root",
        str(workspace.tiingo_root),
        "--storage-namespace",
        workspace.manifest.storage_namespace,
        "--max-symbols",
        str(args.max_symbols),
        "--target-config",
        str(target),
    ]
    completed = subprocess.run(command, cwd=repository_root, check=False)
    if completed.returncode != 0:
        return completed.returncode

    status = repository_root / "scripts" / "research_50_status.py"
    return subprocess.run(
        [sys.executable, str(status), "--root", str(workspace.root)],
        cwd=repository_root,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
