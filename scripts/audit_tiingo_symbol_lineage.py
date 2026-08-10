"""Audit derived Tiingo coverage starts against explicit symbol-lineage seed cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.data.providers.tiingo_lineage_audit import (
    TiingoLineageAuditError,
    audit_tiingo_profile_lineage,
    load_lineage_cases,
    persist_tiingo_lineage_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("configs/tiingo_symbol_lineage_cases_v0.1.json"),
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    cases_path = args.cases if args.cases.is_absolute() else repository_root / args.cases
    profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
    output = root / "evidence" / "tiingo-lineage" / "audit.json"

    try:
        cases = load_lineage_cases(cases_path)
        audit = audit_tiingo_profile_lineage(profile_path=profile_path, cases=cases)
        persist_tiingo_lineage_audit(output, audit)
    except TiingoLineageAuditError as exc:
        raise SystemExit(f"Tiingo lineage audit error: {exc}") from exc

    counts: dict[str, int] = {}
    for item in audit.observations:
        counts[item.classification] = counts.get(item.classification, 0) + 1
    print(
        json.dumps(
            {
                "audit_path": str(output),
                "case_count": audit.case_count,
                "profiled_case_count": audit.profiled_case_count,
                "classification_counts": counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
