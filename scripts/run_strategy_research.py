"""Run an ad hoc feature-expression strategy against one immutable canonical dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    available_strategy_features,
    run_feature_strategy_research,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run exploratory point-in-time strategy research on the already canonical dataset. "
            "No market-data provider calls are made."
        )
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root")
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--expression", default=None)
    parser.add_argument("--strategy-id", default="adhoc-feature-strategy-v0.1")
    parser.add_argument("--name", default="Ad hoc feature strategy")
    parser.add_argument("--description", default="User-supplied exploratory feature expression")
    parser.add_argument("--rank-feature", default="return_20")
    parser.add_argument("--ascending", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--horizons", default="5,20,60")
    parser.add_argument("--start", default=None, help="First signal date, YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Last signal date, YYYY-MM-DD")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated reviewed symbols; default is every instrument in the dataset",
    )
    parser.add_argument("--identity-candidate", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--list-features", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.list_features:
        print("\n".join(available_strategy_features()))
        return 0
    if args.expression is None or not args.expression.strip():
        raise SystemExit("--expression is required unless --list-features is used")

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)

    dataset_version = args.dataset_version or workspace.manifest.canonical_dataset_version
    if dataset_version is None:
        raise SystemExit("operator workspace has no selected canonical dataset")

    canonical = CanonicalDailyBarStore(workspace.canonical_root).load(
        DatasetVersion(dataset_version)
    )
    selected = canonical
    symbol_by_instrument: dict[str, str] = {}
    requested_symbols = _symbols(args.symbols)
    identity_path = args.identity_candidate or (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    if identity_path.is_file():
        candidate = load_reviewed_identity_snapshot_candidate(identity_path)
        blocked = {str(item.instrument_id) for item in candidate.coverage_gaps}
        symbol_by_instrument = {
            str(item.instrument_id): item.query_symbol.upper()
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo" and str(item.instrument_id) not in blocked
        }

    if requested_symbols:
        if not symbol_by_instrument:
            raise SystemExit("--symbols requires a reviewed identity candidate for symbol resolution")
        instrument_by_symbol = {symbol: instrument for instrument, symbol in symbol_by_instrument.items()}
        missing = tuple(symbol for symbol in requested_symbols if symbol not in instrument_by_symbol)
        if missing:
            raise SystemExit("unknown or blocked reviewed symbols: " + ", ".join(missing))
        selected_ids = {instrument_by_symbol[symbol] for symbol in requested_symbols}
        selected = tuple(item for item in canonical if str(item.instrument_id) in selected_ids)
        if not selected:
            raise SystemExit("selected symbols have no rows in the canonical dataset")

    strategy = StrategyDefinition(
        strategy_id=args.strategy_id,
        name=args.name,
        description=args.description,
        expression=args.expression,
        rank_feature=args.rank_feature,
        descending=not args.ascending,
        per_session_limit=args.limit,
    )
    horizons = _horizons(args.horizons)
    report = run_feature_strategy_research(
        selected,
        strategy=strategy,
        horizons=horizons,
        signal_start=_date(args.start),
        signal_end=_date(args.end),
    )

    payload = {
        "schema_version": "strategy-research-operator-v0.1",
        "provider_calls_made": False,
        "dataset_version": dataset_version,
        "symbol_by_instrument": symbol_by_instrument,
        "report": asdict(report),
    }
    logical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    checksum = hashlib.sha256(logical.encode("utf-8")).hexdigest()
    payload["report_checksum_sha256"] = checksum

    output = args.output or (
        workspace.root
        / "evidence"
        / "research-strategies"
        / f"{_safe_slug(dataset_version)}__{_safe_slug(strategy.strategy_id)}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)

    print(
        json.dumps(
            {
                "dataset_version": report.dataset_version,
                "feature_set_version": report.feature_set_version,
                "instrument_count": report.instrument_count,
                "signal_count": report.signal_count,
                "horizons": list(report.horizons),
                "summaries": [asdict(item) for item in report.summaries],
                "provider_calls_made": False,
                "research_state": report.research_state,
                "report_checksum_sha256": checksum,
                "report_path": str(output),
            },
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )
    return 0


def _symbols(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    result = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    if len(result) != len(set(result)):
        raise SystemExit("--symbols contains duplicates")
    return result


def _horizons(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise SystemExit("--horizons must be comma-separated positive integers") from exc
    if not result or any(item < 1 for item in result) or len(result) != len(set(result)):
        raise SystemExit("--horizons must contain unique positive integers")
    return result


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit("dates must use YYYY-MM-DD") from exc


def _safe_slug(value: str) -> str:
    result = "".join(character if character.isalnum() or character in "-_." else "_" for character in value)
    return result[:128] or "research"


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, Enum)):
        return value.isoformat() if isinstance(value, date) else value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
