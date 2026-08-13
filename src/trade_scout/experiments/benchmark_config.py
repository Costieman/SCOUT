"""Load checked-in explicit benchmark definitions for governed research execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.data.providers.tiingo_benchmark import TiingoBenchmarkDefinition

_BENCHMARK_CONFIG_SCHEMA = "experiment-a-benchmark-v0.1"
_EXPECTED_FIELDS = frozenset(
    {
        "schema_version",
        "benchmark_version",
        "purpose",
        "provider_id",
        "query_symbol",
        "provider_instrument_id",
        "instrument_id",
        "name",
        "exchange",
        "currency",
        "first_trade_date",
        "coverage_start_date",
        "coverage_end_date",
        "dataset_id",
        "dataset_version",
        "benchmark_target",
        "evidence_refs",
        "scope_notes",
    }
)


class BenchmarkConfigError(ValueError):
    """Raised when a checked-in research benchmark definition is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class ExperimentABenchmarkConfig:
    """Validated metadata plus the canonical benchmark promotion definition."""

    benchmark_version: str
    purpose: str
    provider_id: str
    benchmark_target: str
    evidence_refs: tuple[str, ...]
    scope_notes: tuple[str, ...]
    definition: TiingoBenchmarkDefinition


def load_experiment_a_benchmark_config(path: Path) -> ExperimentABenchmarkConfig:
    """Load one exact-schema benchmark config without silently accepting unknown fields."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BenchmarkConfigError(f"cannot read benchmark config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkConfigError("benchmark config is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise BenchmarkConfigError("benchmark config root must be an object")
    fields = frozenset(raw)
    if fields != _EXPECTED_FIELDS:
        missing = ", ".join(sorted(_EXPECTED_FIELDS - fields))
        extra = ", ".join(sorted(fields - _EXPECTED_FIELDS))
        raise BenchmarkConfigError(
            f"benchmark config fields differ from schema; missing={missing}; extra={extra}"
        )
    if _text(raw, "schema_version") != _BENCHMARK_CONFIG_SCHEMA:
        raise BenchmarkConfigError("unsupported benchmark config schema_version")
    provider_id = _text(raw, "provider_id")
    if provider_id != "tiingo":
        raise BenchmarkConfigError("Experiment A benchmark config currently supports Tiingo only")

    try:
        definition = TiingoBenchmarkDefinition(
            query_symbol=_text(raw, "query_symbol"),
            provider_instrument_id=_text(raw, "provider_instrument_id"),
            instrument_id=InstrumentId(_text(raw, "instrument_id")),
            name=_text(raw, "name"),
            exchange=_text(raw, "exchange"),
            currency=_text(raw, "currency"),
            first_trade_date=_date(raw, "first_trade_date"),
            dataset_start_date=_date(raw, "coverage_start_date"),
            dataset_end_date=_date(raw, "coverage_end_date"),
            dataset_version=DatasetVersion(_text(raw, "dataset_version")),
            dataset_id=_text(raw, "dataset_id"),
        )
    except ValueError as exc:
        raise BenchmarkConfigError(str(exc)) from exc

    return ExperimentABenchmarkConfig(
        benchmark_version=_text(raw, "benchmark_version"),
        purpose=_text(raw, "purpose"),
        provider_id=provider_id,
        benchmark_target=_text(raw, "benchmark_target"),
        evidence_refs=_text_tuple(raw, "evidence_refs"),
        scope_notes=_text_tuple(raw, "scope_notes"),
        definition=definition,
    )


def _text(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkConfigError(f"benchmark config field {key} must be non-empty text")
    return value.strip()


def _text_tuple(values: dict[str, object], key: str) -> tuple[str, ...]:
    value = values.get(key)
    if not isinstance(value, list) or not value:
        raise BenchmarkConfigError(f"benchmark config field {key} must be a non-empty list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BenchmarkConfigError(f"benchmark config field {key} contains invalid text")
        result.append(item.strip())
    if len(set(result)) != len(result):
        raise BenchmarkConfigError(f"benchmark config field {key} contains duplicates")
    return tuple(result)


def _date(values: dict[str, object], key: str) -> date:
    text = _text(values, key)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise BenchmarkConfigError(f"benchmark config field {key} is not an ISO date") from exc
