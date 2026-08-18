"""HTTP adapters for explicit research-brain views and mutations."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlencode

from trade_scout.app.research_brain_checkpoints import ResearchBrainCheckpointError
from trade_scout.app.research_brain_followups import ResearchBrainFollowUpError
from trade_scout.app.research_brain_service import (
    ResearchBrainWorkbenchService,
    parse_focus_rules,
)
from trade_scout.app.research_brain_surface import render_research_brains_html
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.experiments.research_brains import ResearchBrainError

_MAX_FORM_BYTES = 64 * 1024


def build_research_brains_page(
    query: str,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Build one read-only brain page; GET never creates or changes membership."""

    service = _service(recorder)
    parameters = parse_qs(query, keep_blank_values=True)
    brain_id = _one(parameters, "brain", default="").strip()
    prefill = _one(parameters, "experiment", default="").strip()
    message = _one(parameters, "message", default="").strip() or None
    try:
        detail = service.detail(brain_id) if brain_id else None
        html = render_research_brains_html(
            brains=service.list_brains(),
            detail=detail,
            prefill_experiment_id=prefill,
            message=message,
        )
        return HTTPStatus.OK, html
    except (
        KeyError,
        OSError,
        ValueError,
        ResearchBrainError,
        ResearchBrainCheckpointError,
        ResearchBrainFollowUpError,
    ) as exc:
        html = render_research_brains_html(
            brains=service.list_brains(),
            prefill_experiment_id=prefill,
            error=str(exc),
        )
        return HTTPStatus.BAD_REQUEST, html


def handle_research_brain_post(
    body: bytes,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Apply one explicit local form mutation and return a safe redirect target."""

    if len(body) > _MAX_FORM_BYTES:
        raise ValueError("research-brain form exceeds the 64 KiB safety limit")
    try:
        source = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("research-brain form must be UTF-8") from exc
    parameters = parse_qs(source, keep_blank_values=True, strict_parsing=False)
    action = _one(parameters, "action", default="").strip()
    service = _service(recorder)

    if action == "create":
        definition = service.create_brain(
            name=_required(parameters, "name"),
            research_question=_required(parameters, "research_question"),
            created_by=_required(parameters, "actor"),
            focus_rules=parse_focus_rules(_one(parameters, "focus_rules", default="")),
            notes=_one(parameters, "notes", default="").strip(),
        )
        return HTTPStatus.SEE_OTHER, _redirect_target(
            brain_id=definition.brain_id,
            message=f"Created research brain {definition.name}.",
        )

    if action == "add":
        membership = service.add_experiment(
            brain_id=_required(parameters, "brain_id"),
            experiment_id=_required(parameters, "experiment_id"),
            added_by=_required(parameters, "actor"),
            note=_one(parameters, "note", default="").strip(),
        )
        message = _membership_message(membership.alignment_state.value, membership.experiment_id)
        return HTTPStatus.SEE_OTHER, _redirect_target(
            brain_id=membership.brain_id,
            message=message,
        )

    if action == "checkpoint":
        try:
            checkpoint = service.save_review_checkpoint(
                brain_id=_required(parameters, "brain_id"),
                created_by=_required(parameters, "actor"),
                note=_one(parameters, "note", default="").strip(),
            )
        except ResearchBrainCheckpointError as exc:
            raise ValueError(str(exc)) from exc
        return HTTPStatus.SEE_OTHER, _redirect_target(
            brain_id=checkpoint.brain_id,
            message=f"Saved brain review checkpoint {checkpoint.checkpoint_id}.",
        )

    if action == "draft_follow_up":
        try:
            proposal = service.draft_follow_up_proposal(
                brain_id=_required(parameters, "brain_id"),
                created_by=_required(parameters, "actor"),
            )
        except ResearchBrainFollowUpError as exc:
            raise ValueError(str(exc)) from exc
        return HTTPStatus.SEE_OTHER, _redirect_target(
            brain_id=proposal.brain_id,
            message=(
                f"Drafted follow-up proposal {proposal.proposal_id}. Nothing has been run; review "
                "the plan before approving it."
            ),
        )

    if action == "approve_follow_up":
        try:
            approval = service.approve_follow_up_proposal(
                brain_id=_required(parameters, "brain_id"),
                proposal_id=_required(parameters, "proposal_id"),
                approved_by=_required(parameters, "actor"),
                note=_one(parameters, "note", default="").strip(),
            )
        except ResearchBrainFollowUpError as exc:
            raise ValueError(str(exc)) from exc
        return HTTPStatus.SEE_OTHER, _redirect_target(
            brain_id=approval.brain_id,
            message=(
                f"Approved proposal {approval.proposal_id}. Approval is recorded, but SCOUT has not "
                "executed the proposed research."
            ),
        )

    raise ValueError("unknown research-brain form action")


def render_research_brain_post_error(
    error: Exception,
    recorder: StrategyBuilderExperimentRecorder,
) -> str:
    """Render one mutation error without losing the current brain inventory."""

    service = _service(recorder)
    return render_research_brains_html(
        brains=service.list_brains(),
        error=str(error),
    )


def _service(recorder: StrategyBuilderExperimentRecorder) -> ResearchBrainWorkbenchService:
    return ResearchBrainWorkbenchService(
        experiment_root=recorder.experiment_root,
        brain_root=recorder.experiment_root.parent / "brains",
    )


def _membership_message(alignment: str, experiment_id: str) -> str:
    if alignment == "DRIFT_WARNING":
        return (
            f"Added {experiment_id}. It is outside one or more focus boundaries, so SCOUT kept it "
            "with a scope warning."
        )
    if alignment == "UNASSESSED":
        return (
            f"Added {experiment_id}. This brain has no strict focus boundary to check it against."
        )
    return f"Added {experiment_id} to the research brain."


def _redirect_target(*, brain_id: str, message: str) -> str:
    return "/research/brains?" + urlencode({"brain": brain_id, "message": message})


def _required(parameters: dict[str, list[str]], name: str) -> str:
    value = _one(parameters, name, default="").strip()
    if not value:
        raise ValueError(f"missing form field {name}")
    return value


def _one(
    parameters: dict[str, list[str]],
    name: str,
    *,
    default: str,
) -> str:
    values = parameters.get(name)
    if not values:
        return default
    if len(values) != 1:
        raise ValueError(f"form field {name} must appear once")
    return values[0]


__all__ = [
    "build_research_brains_page",
    "handle_research_brain_post",
    "render_research_brain_post_error",
]
