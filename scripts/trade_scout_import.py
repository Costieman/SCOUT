"""Single operational entry point for resumable Trade Scout imports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.data.import_orchestrator import (
    ImportOrchestrationError,
    run_import_pipeline,
    tiingo_sp500_stage_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--provider", choices=("tiingo",), default="tiingo")
    parser.add_argument("--universe", choices=("sp500",), default="sp500")
    parser.add_argument("--sec-sleep", type=float, default=0.6)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    if args.sec_sleep < 0:
        parser.error("--sec-sleep must be non-negative")

    repository_root = Path(__file__).resolve().parents[1]
    workspace_root = args.root.expanduser().resolve()

    try:
        stages = tiingo_sp500_stage_plan(
            repository_root=repository_root,
            workspace_root=workspace_root,
            sec_sleep=args.sec_sleep,
        )
        state = run_import_pipeline(
            repository_root=repository_root,
            workspace_root=workspace_root,
            provider=args.provider,
            universe=args.universe,
            stages=stages,
            restart=args.restart,
        )
    except ImportOrchestrationError as exc:
        print(f"Trade Scout import failed: {exc}")
        return 2

    summary = {
        "status": "COMPLETE",
        "run_id": state.run_id,
        "provider": state.provider,
        "universe": state.universe,
        "stage_count": len(state.stages),
        "succeeded_stage_count": sum(item.status == "SUCCEEDED" for item in state.stages),
        "state_path": str(
            workspace_root
            / "evidence"
            / "import-runs"
            / f"{state.provider}-{state.universe}"
            / "state.json"
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
