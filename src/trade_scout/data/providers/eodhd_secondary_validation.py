"""Versioned plan for bounded EODHD versus secondary-provider OHLCV validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import InstrumentId
from trade_scout.data.cross_provider_evidence import CrossProviderEvidenceCase


class EodhdSecondaryValidationError(ValueError):
    """Raised when an EODHD secondary-validation plan is malformed."""


@dataclass(frozen=True, slots=True)
class EodhdSecondaryValidationCase:
    """One explicitly linked EODHD/Tiingo raw-OHLCV comparison case."""

    case_id: str
    symbol: str
    instrument_id: InstrumentId
    eodhd_provider_instrument_id: str
    tiingo_provider_instrument_id: str
    start: date
    end: date

    def __post_init__(self) -> None:
        for name, value in (
            ("case_id", self.case_id),
            ("symbol", self.symbol),
            ("eodhd_provider_instrument_id", self.eodhd_provider_instrument_id),
            ("tiingo_provider_instrument_id", self.tiingo_provider_instrument_id),
        ):
            if not value.strip():
                raise EodhdSecondaryValidationError(f"{name} must be non-empty")
        if self.end < self.start:
            raise EodhdSecondaryValidationError("validation case end must be on or after start")

    def evidence_case(self) -> CrossProviderEvidenceCase:
        """Materialize the provider-neutral comparison boundary without weakening identities."""

        return CrossProviderEvidenceCase(
            case_id=self.case_id,
            instrument_id=self.instrument_id,
            primary_provider_id="eodhd",
            primary_provider_instrument_id=self.eodhd_provider_instrument_id,
            secondary_provider_id="tiingo",
            secondary_provider_instrument_id=self.tiingo_provider_instrument_id,
            start=self.start,
            end=self.end,
        )


@dataclass(frozen=True, slots=True)
class EodhdSecondaryValidationPlan:
    """Immutable set of cases whose completion may support secondary-provider acceptance evidence."""

    version: str
    cases: tuple[EodhdSecondaryValidationCase, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise EodhdSecondaryValidationError("validation plan version must be non-empty")
        if not self.cases:
            raise EodhdSecondaryValidationError("validation plan requires at least one case")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise EodhdSecondaryValidationError("validation plan case IDs must be unique")


def load_eodhd_secondary_validation_plan(path: Path) -> EodhdSecondaryValidationPlan:
    """Load a strict plan; unknown or omitted fields are rejected rather than inferred."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EodhdSecondaryValidationError(f"cannot read validation plan: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EodhdSecondaryValidationError("validation plan is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise EodhdSecondaryValidationError("validation plan root must be an object")
    _require_exact_fields(payload, {"version", "cases"}, context="validation plan")
    version = payload["version"]
    raw_cases = payload["cases"]
    if not isinstance(version, str):
        raise EodhdSecondaryValidationError("validation plan version must be text")
    if not isinstance(raw_cases, list):
        raise EodhdSecondaryValidationError("validation plan cases must be an array")
    return EodhdSecondaryValidationPlan(
        version=version,
        cases=tuple(_parse_case(item) for item in raw_cases),
    )


def _parse_case(payload: object) -> EodhdSecondaryValidationCase:
    if not isinstance(payload, dict):
        raise EodhdSecondaryValidationError("validation case must be an object")
    required = {
        "case_id",
        "symbol",
        "instrument_id",
        "eodhd_provider_instrument_id",
        "tiingo_provider_instrument_id",
        "start",
        "end",
    }
    _require_exact_fields(payload, required, context="validation case")
    text_fields: dict[str, str] = {}
    for field in required:
        value = payload[field]
        if not isinstance(value, str):
            raise EodhdSecondaryValidationError(f"validation case {field} must be text")
        text_fields[field] = value
    try:
        start = date.fromisoformat(text_fields["start"])
        end = date.fromisoformat(text_fields["end"])
    except ValueError as exc:
        raise EodhdSecondaryValidationError("validation case dates must use YYYY-MM-DD") from exc
    return EodhdSecondaryValidationCase(
        case_id=text_fields["case_id"],
        symbol=text_fields["symbol"].upper(),
        instrument_id=InstrumentId(text_fields["instrument_id"]),
        eodhd_provider_instrument_id=text_fields["eodhd_provider_instrument_id"],
        tiingo_provider_instrument_id=text_fields["tiingo_provider_instrument_id"],
        start=start,
        end=end,
    )


def _require_exact_fields(
    payload: dict[str, object],
    required: set[str],
    *,
    context: str,
) -> None:
    missing = required - set(payload)
    unknown = set(payload) - required
    if not missing and not unknown:
        return
    details: list[str] = []
    if missing:
        details.append("missing=" + ",".join(sorted(missing)))
    if unknown:
        details.append("unknown=" + ",".join(sorted(unknown)))
    raise EodhdSecondaryValidationError(f"invalid {context} fields: " + "; ".join(details))
