"""Run canonical-only T0-T5 trend-context decomposition on the selected research dataset."""

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
from trade_scout.app.trend_context_edge_family_surface import render_trend_context_edge_family_html
from trade_scout.app.universe_research_service import CanonicalUniverseResearchSource
from trade_scout.validation.trend_context_edge_family import (
    build_trend_context_edge_family_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decompose first-program T0-T5 trend contexts on one immutable canonical fixed cohort. "
            "No market-data provider calls are made and T6 is not inferred without its benchmark."
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--lookback-years", type=int, default=2, choices=(1, 2, 3, 5, 10, 20))
    parser.add_argument("--horizon", type=int, default=20, choices=(2, 3, 5, 10, 20, 40, 60))
    parser.add_argument("--sampling-stride", type=int, default=5)
    parser.add_argument("--sma-slope-lookback", type=int, default=20)
    parser.add_argument("--trailing-return-intervals", type=int, default=60)
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    parser.add_argument("--randomization-iterations", type=int, default=10_000)
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

    source = CanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    print("Loading reviewed canonical universe...", flush=True)
    series = source.research_series("reviewed_canonical")
    latest = max(bars[-1].trade_date for bars in series.values())
    start = _subtract_years(latest, args.lookback_years)
    print(
        f"Running canonical-only T0-T5 trend decomposition across {len(series)} instruments "
        f"({start.isoformat()} to {latest.isoformat()}) at {args.horizon} sessions.",
        flush=True,
    )
    report = build_trend_context_edge_family_report(
        series,
        universe_id="reviewed_canonical",
        universe_label=source.available_universes()[0].label,
        analysis_start=start,
        analysis_end=latest,
        horizon=args.horizon,
        sampling_stride=args.sampling_stride,
        sma_slope_lookback=args.sma_slope_lookback,
        trailing_return_intervals=args.trailing_return_intervals,
        relative_strength_intervals=args.trailing_return_intervals,
        bootstrap_resamples=args.bootstrap_resamples,
        randomization_iterations=args.randomization_iterations,
        random_seed=args.seed,
        alpha=args.alpha,
        progress=lambda message: print(message, flush=True),
    )

    payload = {
        "schema_version": "trend-context-edge-family-operator-v0.1",
        "provider_calls_made": False,
        "report": asdict(report),
    }
    logical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    checksum = hashlib.sha256(logical.encode("utf-8")).hexdigest()
    payload["report_checksum_sha256"] = checksum

    output_dir = args.output_dir or workspace.root / "evidence" / "trend-context-edge-family"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_slug(dataset_version)}__T0-T5__h{args.horizon}__stride{args.sampling_stride}"
    json_path = output_dir / f"{stem}.json"
    html_path = output_dir / f"{stem}.html"
    _atomic_write(
        json_path,
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
    )
    _atomic_write(
        html_path,
        render_trend_context_edge_family_html(report, report_checksum=checksum),
    )

    print("\nTrend context family summary", flush=True)
    print(
        json.dumps(
            {
                "dataset_version": report.dataset_version,
                "research_state": report.research_state,
                "verdict_code": report.verdict.code,
                "verdict": report.verdict.headline,
                "candidate_contexts": [item.value for item in report.candidate_contexts],
                "t6_market_benchmark_status": report.t6_market_benchmark_status,
                "multiplicity_method": report.multiplicity_method.value,
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
