"""Render the combined Phase 1 data-foundation and canonical-provider readiness gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.data.phase_readiness import load_phase1_readiness

_DEFAULT_DATA_LEDGER = Path("configs/data_foundation_acceptance_v0.1.json")
_DEFAULT_PROVIDER_LEDGER = Path("configs/provider_acceptance_eodhd_v0.1.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate whether Trade Scout Phase 1 is ready to hand off to Phase 2."
    )
    parser.add_argument("--data-ledger", type=Path, default=_DEFAULT_DATA_LEDGER)
    parser.add_argument("--provider-ledger", type=Path, default=_DEFAULT_PROVIDER_LEDGER)
    parser.add_argument("--output-root", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = load_phase1_readiness(
        data_ledger_path=args.data_ledger,
        provider_ledger_path=args.provider_ledger,
    )
    payload = {
        "phase_complete": report.phase_complete,
        "data_assessment_version": report.data_assessment_version,
        "provider_id": report.provider_report.provider_id,
        "provider_assessment_version": report.provider_report.assessment_version,
        "data_foundation_complete": report.data_report.phase_complete,
        "canonical_provider_accepted": report.provider_report.accepted,
        "blockers": list(report.blockers),
    }
    markdown = _markdown(payload)
    if args.output_root is not None:
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "phase1-readiness.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (args.output_root / "phase1-readiness.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if report.phase_complete else 2


def _markdown(payload: dict[str, object]) -> str:
    blockers = payload["blockers"]
    if not isinstance(blockers, list):
        raise TypeError("phase readiness blockers must be a list")
    lines = [
        "# Trade Scout Phase 1 readiness",
        "",
        f"Phase complete: **{payload['phase_complete']}**",
        f"Data foundation complete: **{payload['data_foundation_complete']}**",
        f"Canonical provider accepted: **{payload['canonical_provider_accepted']}**",
        f"Canonical provider candidate: `{payload['provider_id']}`",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "Phase 2 may begin only when both underlying gates are complete.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
