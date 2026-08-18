"""HTTP-query adapter for the read-only Experiment Library."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs

from trade_scout.app.experiment_library_service import (
    ExperimentLibraryFilters,
    ExperimentLibraryService,
)
from trade_scout.app.experiment_library_surface import render_experiment_library_html
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.experiments.contracts import ExperimentStatus, ResearchMode


def build_experiment_library_page(
    query: str,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Build one Experiment Library page from private persisted experiment evidence."""

    service = ExperimentLibraryService(recorder.experiment_root)
    parameters = parse_qs(query, keep_blank_values=True)
    filters = ExperimentLibraryFilters()
    try:
        filters = ExperimentLibraryFilters(
            text=_one(parameters, "q", default=""),
            status=_optional_status(parameters),
            mode=_optional_mode(parameters),
            strategy_family=_optional_text(parameters, "strategy_family"),
            dataset_version=_optional_text(parameters, "dataset_version"),
            code_version=_optional_text(parameters, "code_version"),
            hypothesis_family_id=_optional_text(parameters, "hypothesis_family_id"),
        )
        snapshot = service.snapshot(filters)
        detail = None
        experiment_id = _optional_text(parameters, "experiment")
        if experiment_id is not None:
            detail = service.detail(experiment_id)
        compare_ids = tuple(item for item in parameters.get("compare", ()) if item.strip())
        comparison = service.comparison(compare_ids) if compare_ids else ()
        html = render_experiment_library_html(
            snapshot=snapshot,
            strategy_families=service.strategy_families(),
            detail=detail,
            comparison=comparison,
            current_dataset_version=recorder.dataset_version,
        )
        return HTTPStatus.OK, html
    except (KeyError, OSError, ValueError) as exc:
        snapshot = service.snapshot(filters)
        html = render_experiment_library_html(
            snapshot=snapshot,
            strategy_families=service.strategy_families(),
            current_dataset_version=recorder.dataset_version,
            error=str(exc),
        )
        return HTTPStatus.BAD_REQUEST, html


def _optional_status(parameters: dict[str, list[str]]) -> ExperimentStatus | None:
    value = _one(parameters, "status", default="").strip()
    return None if not value else ExperimentStatus(value)


def _optional_mode(parameters: dict[str, list[str]]) -> ResearchMode | None:
    value = _one(parameters, "mode", default="").strip()
    return None if not value else ResearchMode(value)


def _optional_text(parameters: dict[str, list[str]], name: str) -> str | None:
    value = _one(parameters, name, default="").strip()
    return value or None


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
        raise ValueError(f"query parameter {name} must appear once")
    return values[0]


__all__ = ["build_experiment_library_page"]
