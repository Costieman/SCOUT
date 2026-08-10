"""Compare derived Tiingo coverage starts with explicitly sourced symbol-lineage cases."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


class TiingoLineageAuditError(RuntimeError):
    """Raised when lineage cases or derived profile evidence are malformed."""


@dataclass(frozen=True, slots=True)
class LineageEvent:
    effective_date: date
    from_symbol: str | None
    to_symbol: str
    event_type: str
    source_title: str
    source_url: str


@dataclass(frozen=True, slots=True)
class LineageCase:
    source_symbol: str
    current_symbol_effective_date: date
    regular_way_start: date | None
    when_issued_start: date | None
    lineage_events: tuple[LineageEvent, ...]


@dataclass(frozen=True, slots=True)
class LineageAuditObservation:
    source_symbol: str
    observed_first_date: date | None
    current_symbol_effective_date: date
    regular_way_start: date | None
    when_issued_start: date | None
    classification: str
    lineage_events: tuple[LineageEvent, ...]


@dataclass(frozen=True, slots=True)
class TiingoLineageAudit:
    schema_version: str
    profile_path: str
    case_count: int
    profiled_case_count: int
    observations: tuple[LineageAuditObservation, ...]


def load_lineage_cases(path: Path) -> tuple[LineageCase, ...]:
    """Load the checked-in lineage seed cases with strict structure validation."""

    payload = _load_object(path, "lineage case config")
    if payload.get("schema_version") != "tiingo-lineage-audit-cases-v0.1":
        raise TiingoLineageAuditError("unsupported Tiingo lineage case schema")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise TiingoLineageAuditError("Tiingo lineage cases must be an array")

    cases: list[LineageCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise TiingoLineageAuditError("Tiingo lineage case must be an object")
        symbol = _required_text(raw.get("source_symbol"), "source_symbol")
        if symbol in seen:
            raise TiingoLineageAuditError(f"duplicate Tiingo lineage case: {symbol}")
        seen.add(symbol)
        events = _parse_events(raw.get("lineage_events"), symbol)
        cases.append(
            LineageCase(
                source_symbol=symbol,
                current_symbol_effective_date=_required_date(
                    raw.get("current_symbol_effective_date"),
                    "current_symbol_effective_date",
                ),
                regular_way_start=_optional_date(raw.get("regular_way_start"), "regular_way_start"),
                when_issued_start=_optional_date(
                    raw.get("when_issued_start"), "when_issued_start"
                ),
                lineage_events=events,
            )
        )
    return tuple(sorted(cases, key=lambda item: item.source_symbol))


def audit_tiingo_profile_lineage(
    *,
    profile_path: Path,
    cases: tuple[LineageCase, ...],
) -> TiingoLineageAudit:
    """Classify observed provider-history starts without asserting listing completeness."""

    profile = _load_object(profile_path, "Tiingo durable profile")
    if profile.get("schema_version") != "tiingo-durable-profile-v0.1":
        raise TiingoLineageAuditError("unsupported Tiingo durable profile schema")
    raw_symbols = profile.get("symbols")
    if not isinstance(raw_symbols, list):
        raise TiingoLineageAuditError("Tiingo durable profile symbols must be an array")

    observed: dict[str, date | None] = {}
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            raise TiingoLineageAuditError("Tiingo durable profile symbol entry must be an object")
        symbol = _required_text(raw.get("source_symbol"), "source_symbol")
        if symbol in observed:
            raise TiingoLineageAuditError(f"duplicate profile source symbol: {symbol}")
        observed[symbol] = _optional_date(raw.get("first_date"), "first_date")

    observations = tuple(_observe(case, observed.get(case.source_symbol)) for case in cases)
    return TiingoLineageAudit(
        schema_version="tiingo-lineage-audit-v0.1",
        profile_path=str(profile_path),
        case_count=len(cases),
        profiled_case_count=sum(item.observed_first_date is not None for item in observations),
        observations=observations,
    )


def persist_tiingo_lineage_audit(path: Path, audit: TiingoLineageAudit) -> None:
    """Persist derived lineage observations without provider price values."""

    payload = asdict(audit)
    for observation in payload["observations"]:
        observation["observed_first_date"] = _date_text(observation["observed_first_date"])
        observation["current_symbol_effective_date"] = _date_text(
            observation["current_symbol_effective_date"]
        )
        observation["regular_way_start"] = _date_text(observation["regular_way_start"])
        observation["when_issued_start"] = _date_text(observation["when_issued_start"])
        for event in observation["lineage_events"]:
            event["effective_date"] = _date_text(event["effective_date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _observe(case: LineageCase, first: date | None) -> LineageAuditObservation:
    if first is None:
        classification = "NOT_PROFILED"
    elif case.when_issued_start is not None and first == case.when_issued_start:
        classification = "WHEN_ISSUED_START_MATCH"
    elif first < case.current_symbol_effective_date:
        classification = "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED"
    elif case.regular_way_start is not None and first < case.regular_way_start:
        classification = "PRE_REGULAR_WAY_HISTORY_OBSERVED"
    elif first == case.current_symbol_effective_date:
        classification = "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH"
    else:
        classification = "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED"
    return LineageAuditObservation(
        source_symbol=case.source_symbol,
        observed_first_date=first,
        current_symbol_effective_date=case.current_symbol_effective_date,
        regular_way_start=case.regular_way_start,
        when_issued_start=case.when_issued_start,
        classification=classification,
        lineage_events=case.lineage_events,
    )


def _parse_events(value: object, symbol: str) -> tuple[LineageEvent, ...]:
    if not isinstance(value, list) or not value:
        raise TiingoLineageAuditError(f"lineage events must be a non-empty array for {symbol}")
    events: list[LineageEvent] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise TiingoLineageAuditError(f"lineage event must be an object for {symbol}")
        events.append(
            LineageEvent(
                effective_date=_required_date(raw.get("effective_date"), "effective_date"),
                from_symbol=_optional_text(raw.get("from_symbol"), "from_symbol"),
                to_symbol=_required_text(raw.get("to_symbol"), "to_symbol"),
                event_type=_required_text(raw.get("event_type"), "event_type"),
                source_title=_required_text(raw.get("source_title"), "source_title"),
                source_url=_required_text(raw.get("source_url"), "source_url"),
            )
        )
    return tuple(sorted(events, key=lambda item: item.effective_date))


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoLineageAuditError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoLineageAuditError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TiingoLineageAuditError(f"{label} root must be an object")
    return payload


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoLineageAuditError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    text = _required_text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TiingoLineageAuditError(f"{field} must be an ISO date") from exc


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    return _required_date(value, field)


def _date_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, date):
        raise TiingoLineageAuditError("internal lineage date serialization error")
    return value.isoformat()
