"""Generate a readable market-wide edge audit from the selected canonical dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import webbrowser
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.app.readable_edge_surface import render_readable_edge_html
from trade_scout.app.universe_research_service import CanonicalUniverseResearchSource
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.patterns.timeframes import PatternTimeframe
from trade_scout.statistics.readable_edge import build_readable_edge_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a readable preliminary edge audit from the selected immutable canonical "
            "dataset. No market-data provider calls are made."
        )
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root")
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument(
        "--pattern-timeframe",
        default=PatternTimeframe.DAILY.value,
        choices=tuple(item.value for item in PatternTimeframe),
    )
    parser.add_argument("--lookback-years", type=int, default=2, choices=(1, 2, 3, 5, 10, 20))
    parser.add_argument("--horizon", type=int, default=20, choices=(2, 3, 5, 10, 20, 40, 60))
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--max-range-pct", type=float, default=12.0)
    parser.add_argument(
        "--trend-filter",
        default=TrendFilter.ABOVE_SMA_50_100_200.value,
        choices=tuple(item.value for item in TrendFilter),
    )
    parser.add_argument(
        "--volume-ratio",
        default="none",
        help="Breakout-volume ratio or 'none'",
    )
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    parser.add_argument("--random-iterations", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--open-browser", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)
    dataset_version = args.dataset_version or workspace.manifest.canonical_dataset_version
    if dataset_version is None:
        raise SystemExit("operator workspace has no selected canonical dataset")

    identity_candidate = (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    if not identity_candidate.is_file():
        raise SystemExit("reviewed identity candidate is missing")

    source = CanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    series = source.research_series("reviewed_canonical")
    latest = max(bars[-1].trade_date for bars in series.values())
    start = _subtract_years(latest, args.lookback_years)
    config = ConsolidationBreakoutConfig(
        duration=args.duration,
        max_range_pct=args.max_range_pct / 100.0,
        trend_filter=TrendFilter(args.trend_filter),
        cooldown_sessions=5,
        min_breakout_volume_ratio=_volume_ratio(args.volume_ratio),
        volume_lookback_sessions=20,
    )
    report = build_readable_edge_report(
        series,
        universe_id="reviewed_canonical",
        universe_label=source.available_universes()[0].label,
        config=config,
        analysis_start=start,
        analysis_end=latest,
        pattern_timeframe=PatternTimeframe(args.pattern_timeframe),
        selected_horizon=args.horizon,
        bootstrap_resamples=args.bootstrap_resamples,
        random_iterations=args.random_iterations,
        random_seed=args.seed,
    )

    payload = {
        "schema_version": "readable-edge-operator-v0.1",
        "provider_calls_made": False,
        "report": asdict(report),
    }
    logical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    checksum = hashlib.sha256(logical.encode("utf-8")).hexdigest()
    payload["report_checksum_sha256"] = checksum

    output_dir = args.output_dir or workspace.root / "evidence" / "readable-edge"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{_slug(dataset_version)}__{args.pattern_timeframe}__"
        f"d{args.duration}__r{args.max_range_pct:.1f}__h{args.horizon}"
    )
    json_path = output_dir / f"{stem}.json"
    html_path = output_dir / f"{stem}.html"
    _atomic_write(
        json_path,
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
    )
    _atomic_write(html_path, render_readable_edge_html(report, report_checksum=checksum))

    print(
        json.dumps(
            {
                "dataset_version": report.source_report.dataset_version,
                "research_state": report.research_state,
                "verdict_code": report.verdict.code,
                "verdict": report.verdict.headline,
                "raw_mean_return": report.performance.mean_return,
                "raw_mean_interval": asdict(report.performance.mean_interval)
                if report.performance.mean_interval
                else None,
                "simple_baseline_excess": report.simple_baseline.excess_mean_return,
                "random_timing_excess": report.randomized_timing.excess_vs_null_mean,
                "random_timing_p_value": report.randomized_timing.one_sided_p_value,
                "positive_parameter_cells": report.parameter_robustness.positive_excess_cell_count,
                "searched_parameter_cells": report.parameter_robustness.searched_cell_count,
                "provider_calls_made": False,
                "report_checksum_sha256": checksum,
                "json_path": str(json_path),
                "html_path": str(html_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.open_browser:
        webbrowser.open(html_path.resolve().as_uri())
    return 0


def _volume_ratio(value: str) -> float | None:
    if value.strip().lower() == "none":
        return None
    try:
        ratio = float(value)
    except ValueError as exc:
        raise SystemExit("--volume-ratio must be positive or 'none'") from exc
    if ratio <= 0:
        raise SystemExit("--volume-ratio must be positive or 'none'")
    return ratio


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _slug(value: str) -> str:
    result = "".join(
        character if character.isalnum() or character in "-_." else "_" for character in value
    )
    return result[:128] or "dataset"


def _json_default(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
