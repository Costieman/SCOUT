"""Review integrity-verified Phase 1 runtime evidence for semantic acceptance support."""

from __future__ import annotations

import argparse
from pathlib import Path

from trade_scout.data.runtime_evidence_manifest import load_runtime_evidence_manifest
from trade_scout.data.semantic_evidence_review import review_semantic_runtime_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify registered runtime evidence, assess known report semantics, and identify "
            "acceptance-promotion candidates without mutating the checked-in ledger."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    registry = load_runtime_evidence_manifest(args.manifest)
    report = review_semantic_runtime_evidence(registry, evidence_root=args.evidence_root)

    print("# Phase 1 semantic runtime-evidence review")
    print()
    print("| artifact | criterion | integrity | semantic status | promotion candidate |")
    print("|---|---|---|---|---|")
    for review in report.reviews:
        semantic_status = review.semantic_status.value if review.semantic_status is not None else "-"
        print(
            f"| {review.artifact.artifact_id} | {review.artifact.criterion.value} | "
            f"{review.integrity_verified} | {semantic_status} | {review.is_promotion_candidate} |"
        )
        if review.assessment_error is not None:
            print(f"  assessment error: {review.assessment_error}")
        elif review.semantic_note is not None:
            print(f"  note: {review.semantic_note}")

    candidates = report.promotion_candidates()
    print()
    print(f"Promotion candidates: {len(candidates)}")
    print("The checked-in acceptance ledger is not modified by this review.")
    return 2 if report.has_invalid_evidence else 0


if __name__ == "__main__":
    raise SystemExit(main())
