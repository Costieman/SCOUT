"""Offline split-only normalization preview for checksum-verified durable Tiingo EOD history.

Tiingo EOD ``splitFactor`` is an event-date split ratio, while Trade Scout's provider/canonical
contracts require a cumulative split-only price multiplier. This module converts the former to the
latter without using Tiingo's dividend-adjusted ``adj*`` fields as canonical prices.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any

from trade_scout.data.contracts import DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.durable_raw_receipt import (
    DurableRawReceipt,
    load_durable_raw_receipt,
    verify_durable_raw_receipt,
)
from trade_scout.data.instrument_storage import InstrumentMasterStore
from trade_scout.data.normalization import normalize_provider_daily_bars_identity_aware
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reviewed_identity_snapshot import (
    ProviderSeriesLink,
    load_reviewed_identity_snapshot_candidate,
)

_TIINGO_SPLIT_DOC_URL = "https://www.tiingo.com/documentation/corporate-actions/splits"
_TIINGO_EOD_DOC_URL = "https://www.tiingo.com/documentation/end-of-day"
_CROSS_CHECK_RELATIVE_TOLERANCE = Decimal("1e-8")


class TiingoSplitPreviewError(RuntimeError):
    """Raised when private Tiingo evidence cannot be transformed or verified safely."""


@dataclass(frozen=True, slots=True)
class TiingoSplitEvent:
    """Non-price split event retained for preview diagnostics."""

    effective_date: date
    split_ratio: float


@dataclass(frozen=True, slots=True)
class TiingoSplitTransform:
    """In-memory provider-bar transform plus non-price validation diagnostics."""

    bars: tuple[ProviderDailyBar, ...]
    split_events: tuple[TiingoSplitEvent, ...]
    dividend_event_count: int
    tiingo_adjusted_cross_check_eligible: bool
    tiingo_adjusted_cross_check_field_count: int
    tiingo_adjusted_cross_check_mismatch_count: int
    tiingo_adjusted_cross_check_max_relative_error: float | None
    cumulative_price_multiplier_min: float
    cumulative_price_multiplier_max: float


@dataclass(frozen=True, slots=True)
class TiingoSplitSymbolPreview:
    """Workspace-safe diagnostics for one reviewed Tiingo continuity series."""

    query_symbol: str
    instrument_id: InstrumentId
    receipt_id: str
    payload_checksum_sha256: str
    row_count: int
    first_date: date
    last_date: date
    split_event_count: int
    dividend_event_count: int
    cumulative_price_multiplier_min: float
    cumulative_price_multiplier_max: float
    tiingo_adjusted_cross_check_eligible: bool
    tiingo_adjusted_cross_check_field_count: int
    tiingo_adjusted_cross_check_mismatch_count: int
    tiingo_adjusted_cross_check_max_relative_error: float | None
    normalized_bar_count: int
    normalization_issue_count: int
    quality_issue_count: int
    normalization_status: QualityStatus
    split_events: tuple[TiingoSplitEvent, ...]


@dataclass(frozen=True, slots=True)
class TiingoSplitOnlyPreview:
    """Metadata-only preview over the promoted reviewed identity seed scope."""

    schema_version: str
    generated_at: datetime
    snapshot_version: str
    instrument_master_logical_sha256: str
    symbol_history_logical_sha256: str
    symbol_count: int
    row_count: int
    split_event_count: int
    dividend_event_count: int
    cross_check_eligible_symbol_count: int
    cross_check_mismatch_field_count: int
    normalization_issue_count: int
    quality_issue_count: int
    validation_passed: bool
    price_rows_promoted: int
    adjustment_semantics: str
    evidence_urls: tuple[str, ...]
    symbols: tuple[TiingoSplitSymbolPreview, ...]


@dataclass(frozen=True, slots=True)
class _ParsedRow:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    split_ratio: Decimal
    dividend_cash: Decimal
    tiingo_adjusted_ohlc: tuple[Decimal, Decimal, Decimal, Decimal]


def build_tiingo_split_only_provider_bars(
    rows: list[dict[str, Any]],
    *,
    query_symbol: str,
    provider_instrument_id: str,
) -> TiingoSplitTransform:
    """Convert Tiingo event split ratios to cumulative split-only price multipliers.

    Tiingo documents ``splitFactor`` on the split ex-date as ``splitTo/splitFrom``. Raw prices on
    that ex-date are already on the post-split basis, so that event applies to earlier rows only.
    Therefore each row's Trade Scout multiplier is the reciprocal product of split ratios on later
    dates. Dividends are retained separately and never enter this multiplier.
    """

    symbol = query_symbol.strip().upper()
    provider_identity = provider_instrument_id.strip()
    if not symbol or not provider_identity:
        raise TiingoSplitPreviewError("query symbol and provider instrument identity are required")
    parsed = tuple(_parse_rows(rows))
    if not parsed:
        raise TiingoSplitPreviewError(f"Tiingo payload for {symbol} is empty")

    dividend_event_count = sum(item.dividend_cash != 0 for item in parsed)
    cross_check_eligible = dividend_event_count == 0
    future_split_product = Decimal("1")
    reverse_bars: list[ProviderDailyBar] = []
    reverse_multipliers: list[Decimal] = []
    split_events: list[TiingoSplitEvent] = []
    cross_check_fields = 0
    cross_check_mismatches = 0
    max_relative_error = Decimal("0")

    for row in reversed(parsed):
        try:
            multiplier = Decimal("1") / future_split_product
        except (DivisionByZero, InvalidOperation) as exc:
            raise TiingoSplitPreviewError("invalid cumulative Tiingo split product") from exc
        if not multiplier.is_finite() or multiplier <= 0:
            raise TiingoSplitPreviewError("cumulative split-only multiplier must be positive")

        computed_adjusted = (
            row.open * multiplier,
            row.high * multiplier,
            row.low * multiplier,
            row.close * multiplier,
        )
        if cross_check_eligible:
            for computed, vendor_adjusted in zip(
                computed_adjusted, row.tiingo_adjusted_ohlc, strict=True
            ):
                cross_check_fields += 1
                relative_error = _relative_error(computed, vendor_adjusted)
                max_relative_error = max(max_relative_error, relative_error)
                if relative_error > _CROSS_CHECK_RELATIVE_TOLERANCE:
                    cross_check_mismatches += 1

        reverse_bars.append(
            ProviderDailyBar(
                provider_id="tiingo",
                provider_instrument_id=provider_identity,
                symbol=symbol,
                trade_date=row.trade_date,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                split_factor=float(multiplier),
                dividend_cash=float(row.dividend_cash),
                adjusted_open=float(computed_adjusted[0]),
                adjusted_high=float(computed_adjusted[1]),
                adjusted_low=float(computed_adjusted[2]),
                adjusted_close=float(computed_adjusted[3]),
            )
        )
        reverse_multipliers.append(multiplier)

        if row.split_ratio != 1:
            split_events.append(
                TiingoSplitEvent(
                    effective_date=row.trade_date,
                    split_ratio=float(row.split_ratio),
                )
            )
            future_split_product *= row.split_ratio
            if not future_split_product.is_finite() or future_split_product <= 0:
                raise TiingoSplitPreviewError(
                    "Tiingo split ratios produce an invalid cumulative product"
                )

    multipliers = tuple(reverse_multipliers)
    return TiingoSplitTransform(
        bars=tuple(reversed(reverse_bars)),
        split_events=tuple(sorted(split_events, key=lambda item: item.effective_date)),
        dividend_event_count=dividend_event_count,
        tiingo_adjusted_cross_check_eligible=cross_check_eligible,
        tiingo_adjusted_cross_check_field_count=cross_check_fields,
        tiingo_adjusted_cross_check_mismatch_count=cross_check_mismatches,
        tiingo_adjusted_cross_check_max_relative_error=(
            float(max_relative_error) if cross_check_eligible else None
        ),
        cumulative_price_multiplier_min=float(min(multipliers)),
        cumulative_price_multiplier_max=float(max(multipliers)),
    )


def preview_durable_tiingo_split_only(
    *,
    receipt_root: Path,
    raw_root: Path,
    storage_namespace: str,
    candidate_path: Path,
    canonical_root: Path,
    generated_at: datetime | None = None,
) -> TiingoSplitOnlyPreview:
    """Build a no-price-output preview over the promoted reviewed Tiingo identity scope."""

    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")

    candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
    if not candidate.promotion_ready:
        raise TiingoSplitPreviewError("reviewed identity candidate still has coverage gaps")
    snapshot = InstrumentMasterStore(canonical_root).load(candidate.snapshot_version)
    if (
        snapshot.instruments != candidate.instruments
        or snapshot.symbol_history != candidate.symbol_history
    ):
        raise TiingoSplitPreviewError(
            "promoted instrument master does not exactly match the reviewed identity candidate"
        )

    links = tuple(item for item in candidate.provider_series_links if item.provider_id == "tiingo")
    if not links:
        raise TiingoSplitPreviewError("reviewed candidate contains no Tiingo provider-series links")
    link_by_symbol = _links_by_query_symbol(links)
    receipts = _receipts_by_subject(receipt_root, frozenset(link_by_symbol))

    symbol_previews: list[TiingoSplitSymbolPreview] = []
    for query_symbol, link in sorted(link_by_symbol.items()):
        receipt = receipts.get(query_symbol)
        if receipt is None:
            raise TiingoSplitPreviewError(
                f"no durable Tiingo receipt found for reviewed query symbol {query_symbol}"
            )
        record = verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace=storage_namespace,
        )
        rows = _read_raw_rows(record.payload_path, query_symbol)
        transform = build_tiingo_split_only_provider_bars(
            rows,
            query_symbol=query_symbol,
            provider_instrument_id=link.provider_series_id,
        )
        normalized = normalize_provider_daily_bars_identity_aware(
            transform.bars,
            instruments=snapshot.instruments,
            symbol_history=snapshot.symbol_history,
            dataset_version=DatasetVersion(
                f"{candidate.snapshot_version}::tiingo-split-only-preview-v0.1"
            ),
        )
        dates = tuple(item.trade_date for item in transform.bars)
        symbol_previews.append(
            TiingoSplitSymbolPreview(
                query_symbol=query_symbol,
                instrument_id=link.instrument_id,
                receipt_id=receipt.receipt_id,
                payload_checksum_sha256=receipt.payload_checksum_sha256,
                row_count=len(transform.bars),
                first_date=min(dates),
                last_date=max(dates),
                split_event_count=len(transform.split_events),
                dividend_event_count=transform.dividend_event_count,
                cumulative_price_multiplier_min=transform.cumulative_price_multiplier_min,
                cumulative_price_multiplier_max=transform.cumulative_price_multiplier_max,
                tiingo_adjusted_cross_check_eligible=(
                    transform.tiingo_adjusted_cross_check_eligible
                ),
                tiingo_adjusted_cross_check_field_count=(
                    transform.tiingo_adjusted_cross_check_field_count
                ),
                tiingo_adjusted_cross_check_mismatch_count=(
                    transform.tiingo_adjusted_cross_check_mismatch_count
                ),
                tiingo_adjusted_cross_check_max_relative_error=(
                    transform.tiingo_adjusted_cross_check_max_relative_error
                ),
                normalized_bar_count=len(normalized.bars),
                normalization_issue_count=len(normalized.normalization_issues),
                quality_issue_count=len(normalized.quality_issues),
                normalization_status=normalized.status,
                split_events=transform.split_events,
            )
        )

    frozen = tuple(sorted(symbol_previews, key=lambda item: item.query_symbol))
    cross_check_mismatches = sum(
        item.tiingo_adjusted_cross_check_mismatch_count for item in frozen
    )
    normalization_issues = sum(item.normalization_issue_count for item in frozen)
    quality_issues = sum(item.quality_issue_count for item in frozen)
    all_rows_normalized = all(item.normalized_bar_count == item.row_count for item in frozen)
    validation_passed = (
        all_rows_normalized
        and normalization_issues == 0
        and quality_issues == 0
        and cross_check_mismatches == 0
        and all(item.normalization_status is QualityStatus.PASS for item in frozen)
    )

    return TiingoSplitOnlyPreview(
        schema_version="tiingo-split-only-preview-v0.1",
        generated_at=timestamp,
        snapshot_version=candidate.snapshot_version,
        instrument_master_logical_sha256=snapshot.manifest.instrument_logical_sha256,
        symbol_history_logical_sha256=snapshot.manifest.symbol_history_logical_sha256,
        symbol_count=len(frozen),
        row_count=sum(item.row_count for item in frozen),
        split_event_count=sum(item.split_event_count for item in frozen),
        dividend_event_count=sum(item.dividend_event_count for item in frozen),
        cross_check_eligible_symbol_count=sum(
            item.tiingo_adjusted_cross_check_eligible for item in frozen
        ),
        cross_check_mismatch_field_count=cross_check_mismatches,
        normalization_issue_count=normalization_issues,
        quality_issue_count=quality_issues,
        validation_passed=validation_passed,
        price_rows_promoted=0,
        adjustment_semantics=(
            "split-only OHLC multiplier = reciprocal product of Tiingo splitFactor event ratios "
            "on later ex-dates; dividends remain separate"
        ),
        evidence_urls=(_TIINGO_SPLIT_DOC_URL, _TIINGO_EOD_DOC_URL),
        symbols=frozen,
    )


def persist_tiingo_split_only_preview(path: Path, preview: TiingoSplitOnlyPreview) -> None:
    """Persist only derived diagnostics and provenance, never raw/adjusted OHLC values."""

    payload = asdict(preview)
    payload["generated_at"] = preview.generated_at.isoformat()
    for symbol in payload["symbols"]:
        symbol["instrument_id"] = str(symbol["instrument_id"])
        symbol["first_date"] = symbol["first_date"].isoformat()
        symbol["last_date"] = symbol["last_date"].isoformat()
        symbol["normalization_status"] = str(symbol["normalization_status"])
        for event in symbol["split_events"]:
            event["effective_date"] = event["effective_date"].isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parse_rows(rows: list[dict[str, Any]]) -> list[_ParsedRow]:
    parsed: list[_ParsedRow] = []
    previous: date | None = None
    for raw in rows:
        trade_date = _date(raw.get("date"), "date")
        if previous is not None and trade_date <= previous:
            raise TiingoSplitPreviewError("Tiingo durable rows must be strictly date-increasing")
        previous = trade_date
        split_ratio = _decimal(raw.get("splitFactor"), "splitFactor")
        if split_ratio <= 0:
            raise TiingoSplitPreviewError("Tiingo splitFactor must be positive")
        parsed.append(
            _ParsedRow(
                trade_date=trade_date,
                open=_decimal(raw.get("open"), "open"),
                high=_decimal(raw.get("high"), "high"),
                low=_decimal(raw.get("low"), "low"),
                close=_decimal(raw.get("close"), "close"),
                volume=_decimal(raw.get("volume"), "volume"),
                split_ratio=split_ratio,
                dividend_cash=_decimal(raw.get("divCash"), "divCash"),
                tiingo_adjusted_ohlc=(
                    _decimal(raw.get("adjOpen"), "adjOpen"),
                    _decimal(raw.get("adjHigh"), "adjHigh"),
                    _decimal(raw.get("adjLow"), "adjLow"),
                    _decimal(raw.get("adjClose"), "adjClose"),
                ),
            )
        )
    return parsed


def _date(value: object, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise TiingoSplitPreviewError(f"Tiingo {field} must be non-empty text")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise TiingoSplitPreviewError(f"Tiingo {field} is not an ISO date") from exc


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TiingoSplitPreviewError(f"Tiingo {field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise TiingoSplitPreviewError(f"Tiingo {field} must be finite")
    result = Decimal(str(value))
    if not result.is_finite():
        raise TiingoSplitPreviewError(f"Tiingo {field} must be finite")
    return result


def _relative_error(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(right), Decimal("1"))
    return abs(left - right) / denominator


def _links_by_query_symbol(
    links: tuple[ProviderSeriesLink, ...],
) -> dict[str, ProviderSeriesLink]:
    result: dict[str, ProviderSeriesLink] = {}
    for link in links:
        symbol = link.query_symbol.upper()
        if symbol in result:
            raise TiingoSplitPreviewError(f"duplicate reviewed Tiingo query link: {symbol}")
        result[symbol] = link
    return result


def _receipts_by_subject(
    receipt_root: Path,
    targets: frozenset[str],
) -> dict[str, DurableRawReceipt]:
    result: dict[str, DurableRawReceipt] = {}
    paths = tuple(sorted(receipt_root.rglob("*.json"))) if receipt_root.exists() else ()
    for path in paths:
        receipt = load_durable_raw_receipt(path)
        if receipt.provider_id != "tiingo" or receipt.subject_key not in targets:
            continue
        if receipt.subject_key in result:
            raise TiingoSplitPreviewError(
                f"multiple durable receipts found for reviewed Tiingo symbol {receipt.subject_key}"
            )
        result[receipt.subject_key] = receipt
    return result


def _read_raw_rows(path: Path, symbol: str) -> list[dict[str, Any]]:
    try:
        raw: object = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TiingoSplitPreviewError(
            f"verified Tiingo payload is unreadable for {symbol}"
        ) from exc
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise TiingoSplitPreviewError(f"verified Tiingo payload shape is invalid for {symbol}")
    return raw


__all__ = [
    "TiingoSplitEvent",
    "TiingoSplitOnlyPreview",
    "TiingoSplitPreviewError",
    "TiingoSplitSymbolPreview",
    "TiingoSplitTransform",
    "build_tiingo_split_only_provider_bars",
    "persist_tiingo_split_only_preview",
    "preview_durable_tiingo_split_only",
]
