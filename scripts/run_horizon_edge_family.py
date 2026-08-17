"""Run the controlled holding-horizon edge family on the selected canonical dataset."""

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

from trade_scout.app.horizon_edge_family_surface import render_horizon_edge_family_html
from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.app.universe_research_service import CanonicalUniverseResearchSource
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.patterns.timeframes import PatternTimeframe
from trade_scout.validation.horizon_edge_family import build_horizon_edge_family_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a fixed consolidation-breakout definition across a predeclared "
            "holding-horizon family with randomized-timing controls and Benjamini-Hochberg "
            "correction."
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
    parser.add_argument("--horizons", default="2,3,5,10,20,40,60")
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--max-range-pct", type=float, default=12.0)
    parser.add_argument(
        "--trend-filter",
        default=TrendFilter.ABOVE_SMA_50_100_200.value,
        choices=tuple(item.value for item in TrendFilter),
    )
    parser.add_argument("--volume-ratio", default="none")
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    parser.add_argument("--random-iterations", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--alpha", type=float, default=0.05)
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

    horizons = _horizons(args.horizons)
    source = CanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    print("Loading reviewed canonical universe...", flush=True)
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
    print(
        f"Running {len(horizons)}-horizon family across {len(series)} reviewed instruments "
        f"({start.isoformat()} to {latest.isoformat()}).",
        flush=True,
    )
    report = build_horizon_edge_family_report(
        series,
        universe_id="reviewed_canonical",
        universe_label=source.available_universes()[0].label,
        config=config,
        analysis_start=start,
        analysis_end=latest,
        pattern_timeframe=PatternTimeframe(args.pattern_timeframe),
        horizons=horizons,
        bootstrap_resamples=args.bootstrap_resamples,
        random_iterations=args.random_iterations,
        random_seed=args.seed,
        alpha=args.alpha,
        progress=lambda message: print(message, flush=True),
    )

    payload = {
        "schema_version": "horizon-edge-family-operator-v0.1",
        "provider_calls_made": False,
        "report": asdict(report),
    }
    logical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    checksum = hashlib.sha256(logical.encode("utf-8")).hexdigest()
    payload["report_checksum_sha256"] = checksum

    output_dir = args.output_dir or workspace.root / "evidence" / "horizon-edge-family"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{_slug(dataset_version)}__{args.pattern_timeframe}__d{args.duration}__"
        f"r{args.max_range_pct:.1f}__h{'-'.join(str(value) for value in horizons)}"
    )
    json_path = output_dir / f"{stem}.json"
    html_path = output_dir / f"{stem}.html"
    _atomic_write(
        json_path,
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
    )
    _atomic_write(html_path, render_horizon_edge_family_html(report, report_checksum=checksum))

    print("\nHorizon family summary", flush=True)
    print(
        json.dumps(
            {
                "dataset_version": report.dataset_version,
                "research_state": report.research_state,
                "verdict_code": report.verdict.code,
                "verdict": report.verdict.headline,
                "candidate_horizons": report.candidate_horizons,
                "lowest_adjusted_p_horizon": report.lowest_adjusted_p_horizon,
                "best_observed_random_excess_horizon": report.best_observed_random_excess_horizon,
                "multiplicity_method": report.multiplicity_method.value,
                "broader_research_family_correction_status": (
                    report.broader_research_family_correction_status
                ),
                "out_of_sample_status": report.out_of_sample_status,
                "provider_calls_made": False,
                "report_checksum_sha256": checksum,
                "json_path": str(json_path),
                "html_path": str(html_path),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    if args.open_browser:
        opened = webbrowser.open(html_path.resolve().as_uri())
        print(
            "Browser open request sent." if opened else f"Open manually: {html_path}",
            flush=True,
        )
    return 0


def _horizons(value: str) -> tuple[int, ...]:
    try:
        horizons = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise SystemExit("--horizons must be a comma-separated list of positive integers") from exc
    if not horizons or any(item < 1 for item in horizons) or len(set(horizons)) != len(horizons):
        raise SystemExit("--horizons must contain unique positive integers")
    return horizons


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
