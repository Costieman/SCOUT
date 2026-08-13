"""Promote the checked-in Experiment A benchmark definition through the Tiingo operator path."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from trade_scout.experiments.benchmark_config import (
    BenchmarkConfigError,
    load_experiment_a_benchmark_config,
)

_DEFAULT_CONFIG = "configs/experiment_a_spy_benchmark_v0.1.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote the checked-in Experiment A market benchmark into its standalone immutable "
            "canonical dataset."
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(_DEFAULT_CONFIG))
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    config_path = (
        args.config if args.config.is_absolute() else (repository_root / args.config)
    ).resolve()
    try:
        config = load_experiment_a_benchmark_config(config_path)
    except BenchmarkConfigError as exc:
        print(f"Experiment A benchmark config error: {exc}", file=sys.stderr)
        return 2

    definition = config.definition
    command = [
        sys.executable,
        str(repository_root / "scripts" / "promote_tiingo_benchmark.py"),
        "--root",
        str(args.root),
        "--symbol",
        definition.query_symbol,
        "--provider-instrument-id",
        definition.provider_instrument_id,
        "--instrument-id",
        str(definition.instrument_id),
        "--name",
        definition.name,
        "--exchange",
        definition.exchange,
        "--currency",
        definition.currency,
        "--first-trade-date",
        definition.first_trade_date.isoformat(),
        "--start-date",
        definition.dataset_start_date.isoformat(),
        "--end-date",
        definition.dataset_end_date.isoformat(),
        "--dataset-version",
        str(definition.dataset_version),
        "--dataset-id",
        definition.dataset_id,
    ]
    completed = subprocess.run(command, cwd=repository_root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
