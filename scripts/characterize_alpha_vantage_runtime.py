"""Summarize already captured Alpha Vantage raw responses without making provider calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trade_scout.data.alpha_vantage_characterization import (
    characterize_raw_root,
    summarize_characterization,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify captured Alpha Vantage responses without issuing new API requests."
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("runtime/alpha-vantage-evaluation/raw"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/alpha-vantage-evaluation/report/response-characterization.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    responses = characterize_raw_root(args.raw_root)
    summary = summarize_characterization(responses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
