"""Render the checked-in Phase 1 data-foundation acceptance ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidenceStatus
from trade_scout.data.acceptance_ledger import load_acceptance_ledger

_DEFAULT_LEDGER = Path("configs/data_foundation_acceptance_v0.1.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and report the Trade Scout Phase 1 data-foundation acceptance gate."
    )
    parser.add_argument("--ledger", type=Path, default=_DEFAULT_LEDGER)
    parser.add_argument("--output-root", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    ledger = load_acceptance_ledger(args.ledger)
    report = ledger.report
    status_counts = {
        status.value: sum(item.status is status for item in report.evidence)
        for status in AcceptanceEvidenceStatus
    }
    payload = {
        "assessment_version": ledger.assessment_version,
        "phase_complete": report.phase_complete,
        "status_counts": status_counts,
        "criteria": [
            {
                "criterion": item.criterion.value,
                "status": item.status.value,
                "evidence": list(item.evidence),
                "note": item.note,
            }
            for item in report.evidence
        ],
        "unresolved_criteria": [item.criterion.value for item in report.unresolved],
    }
    markdown = _markdown(payload)
    if args.output_root is not None:
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "data-foundation-acceptance.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (args.output_root / "data-foundation-acceptance.md").write_text(
            markdown,
            encoding="utf-8",
        )
    print(markdown)
    return 0 if report.phase_complete else 2


def _markdown(payload: dict[str, object]) -> str:
    criteria = payload["criteria"]
    if not isinstance(criteria, list):
        raise TypeError("acceptance report criteria must be a list")
    lines = [
        "# Phase 1 data-foundation acceptance",
        "",
        f"Assessment: `{payload['assessment_version']}`",
        f"Phase complete: **{payload['phase_complete']}**",
        "",
        "| criterion | status |",
        "|---|---|",
    ]
    for raw_item in criteria:
        if not isinstance(raw_item, dict):
            raise TypeError("acceptance criterion report item must be an object")
        lines.append(f"| {raw_item['criterion']} | {raw_item['status']} |")
    lines.extend(["", "## Unresolved evidence", ""])
    unresolved = [item for item in criteria if item.get("status") != "DEMONSTRATED"]
    if not unresolved:
        lines.append("- None.")
    else:
        for item in unresolved:
            lines.append(f"- **{item['criterion']} — {item['status']}:** {item['note']}")
    lines.extend(
        [
            "",
            "This report is evidence-conservative: implementation artifacts do not automatically "
            "substitute for required live-provider or representative-data demonstrations.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
