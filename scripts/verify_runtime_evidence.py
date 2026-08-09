"""Verify registered Phase 1 runtime evidence artifacts by exact checksum."""

from __future__ import annotations

import argparse
from pathlib import Path

from trade_scout.data.runtime_evidence_manifest import load_runtime_evidence_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a Trade Scout runtime-evidence manifest against a local evidence root."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    registry = load_runtime_evidence_manifest(args.manifest)
    verifications = registry.verify(args.evidence_root)
    print("# Phase 1 runtime evidence verification")
    print()
    print("| artifact | criterion | verified |")
    print("|---|---|---|")
    for verification in verifications:
        print(
            f"| {verification.artifact.artifact_id} | "
            f"{verification.artifact.criterion.value} | {verification.verified} |"
        )
    failed = [verification for verification in verifications if not verification.verified]
    if failed:
        print()
        print("Verification failed closed for:")
        for verification in failed:
            print(f"- {verification.artifact.artifact_id}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
