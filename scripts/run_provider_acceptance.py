"""Report one checked-in provider-specific acceptance assessment."""

from __future__ import annotations

import argparse
from pathlib import Path

from trade_scout.data.provider_acceptance import load_provider_acceptance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate whether one provider has satisfied every canonical-provider gate."
    )
    parser.add_argument("assessment", type=Path)
    return parser


def main() -> int:
    report = load_provider_acceptance(_parser().parse_args().assessment)
    print(f"# Provider acceptance: {report.provider_id}")
    print()
    print(f"Assessment: `{report.assessment_version}`")
    print(f"Accepted: **{str(report.accepted).lower()}**")
    print()
    print("| criterion | status | note |")
    print("|---|---|---|")
    for item in report.evidence:
        print(f"| {item.criterion.value} | {item.status.value} | {item.note} |")
    print()
    print(f"Unresolved criteria: {len(report.unresolved)}")
    return 0 if report.accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
