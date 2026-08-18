"""Create and inspect focused research-brain collections in a private operator workspace."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.experiments.contracts import JSONScalar
from trade_scout.experiments.research_brains import (
    BrainFocusRule,
    FileResearchBrainStore,
    ResearchBrainDefinition,
    ResearchBrainError,
)
from trade_scout.experiments.serialization import to_json_value
from trade_scout.experiments.store import FileManifestStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage append-only SCOUT research brains over existing immutable experiment records. "
            "This command never launches market-data provider calls or promotes research."
        )
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create one immutable research-brain focus")
    create.add_argument("--brain-id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--created-by", required=True)
    create.add_argument(
        "--focus",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help=(
            "Optional exact resolved-configuration focus rule. Repeat for multiple paths. "
            "Experiments outside these rules are retained with a DRIFT_WARNING, not rejected."
        ),
    )
    create.add_argument("--notes", default="")

    add = subparsers.add_parser("add", help="Add one terminal experiment to a brain")
    add.add_argument("--brain-id", required=True)
    add.add_argument("--experiment-id", required=True)
    add.add_argument("--added-by", required=True)
    add.add_argument("--note", default="")

    show = subparsers.add_parser("show", help="Show one brain and its full preserved history")
    show.add_argument("--brain-id", required=True)

    subparsers.add_parser("list", help="List all research brains")
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace = load_operator_workspace(root)
    brain_store = FileResearchBrainStore(workspace.root / "research" / "brains")

    try:
        if args.command == "create":
            rules = tuple(_parse_focus_rule(item) for item in args.focus)
            definition = ResearchBrainDefinition(
                brain_id=args.brain_id,
                name=args.name,
                research_question=args.question,
                created_by=args.created_by,
                created_at=datetime.now(UTC).isoformat(),
                focus_rules=rules,
                notes=args.notes,
            )
            checksum = brain_store.create(definition)
            _print({"definition": definition, "checksum": checksum})
            return 0

        if args.command == "add":
            experiment_store = FileManifestStore(workspace.root / "research" / "experiments")
            manifest = experiment_store.read_manifest(args.experiment_id)
            membership = brain_store.add_experiment(
                args.brain_id,
                manifest,
                added_by=args.added_by,
                note=args.note,
            )
            _print(membership)
            return 0

        if args.command == "show":
            _print(brain_store.snapshot(args.brain_id))
            return 0

        if args.command == "list":
            payload = []
            for definition in brain_store.list_brains():
                snapshot = brain_store.snapshot(definition.brain_id)
                payload.append(
                    {
                        "brain_id": definition.brain_id,
                        "name": definition.name,
                        "research_question": definition.research_question,
                        "membership_count": len(snapshot.memberships),
                        "succeeded_count": snapshot.succeeded_count,
                        "failed_count": snapshot.failed_count,
                        "drift_warning_count": snapshot.drift_warning_count,
                        "conditioning_readiness": snapshot.conditioning_readiness,
                    }
                )
            _print(payload)
            return 0
    except (OSError, ValueError, KeyError, ResearchBrainError) as exc:
        raise SystemExit(f"research brain error: {exc}") from exc

    raise SystemExit(f"unsupported research brain command: {args.command}")


def _parse_focus_rule(source: str) -> BrainFocusRule:
    if "=" not in source:
        raise ValueError("--focus must use PATH=VALUE")
    path, raw_value = source.split("=", 1)
    path = path.strip()
    if not path or not raw_value.strip():
        raise ValueError("--focus requires a non-empty path and value")
    value = _parse_scalar(raw_value.strip())
    return BrainFocusRule(
        configuration_path=path,
        allowed_values=(value,),
        rationale=f"Declared focus boundary for {path}.",
    )


def _parse_scalar(source: str) -> JSONScalar:
    try:
        value = json.loads(source)
    except json.JSONDecodeError:
        value = source
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("--focus VALUE must be a JSON scalar or plain string")


def _print(value: object) -> None:
    print(json.dumps(to_json_value(value), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
