"""Materialize the unresolved Tiingo queue without touching locked reviewed symbols."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from trade_scout.data.remaining_identity_queue import (
    RemainingIdentityQueueError,
    build_remaining_identity_queue,
    persist_remaining_identity_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    reviewed = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    remaining = root / "evidence" / "deferred-resolution" / "extended" / "remaining.json"
    output = root / "evidence" / "deferred-resolution" / "remaining-only" / "queue.json"

    try:
        summary = build_remaining_identity_queue(
            reviewed_candidate_path=reviewed,
            extended_remaining_path=remaining,
        )
        persist_remaining_identity_queue(output, summary)
        payload = asdict(summary)
        payload["queued_symbols"] = list(summary.queued_symbols)
        payload.update(
            {
                "status": "READY_FOR_NEXT_RESOLVER",
                "canonical_state_mutated": False,
                "provider_calls_made": False,
                "sec_calls_made": False,
                "queue_path": str(output),
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (RemainingIdentityQueueError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"remaining Tiingo identity queue error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
