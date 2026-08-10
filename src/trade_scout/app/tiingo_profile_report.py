# ruff: noqa: E501
"""Render private-workspace Tiingo profile evidence without raw market-data values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path


class TiingoProfileReportError(RuntimeError):
    """Raised when derived Tiingo profile evidence is malformed or inconsistent."""


_STRUCTURAL_FIELDS = (
    "invalid_date_row_count",
    "duplicate_date_count",
    "non_monotonic_date_count",
    "missing_required_field_row_count",
    "invalid_numeric_row_count",
    "ohlc_invariant_violation_count",
    "negative_volume_count",
    "long_calendar_gap_count",
)


@dataclass(frozen=True, slots=True)
class TiingoProfileRow:
    """Presentation-safe diagnostics for one profiled acquisition subject."""

    source_symbol: str
    row_count: int
    first_date: str | None
    last_date: str | None
    split_event_count: int
    dividend_event_count: int
    structural_anomaly_count: int


@dataclass(frozen=True, slots=True)
class TiingoProfileView:
    """Strict, presentation-ready view over one derived profile artifact."""

    generated_at: str
    symbol_count: int
    total_row_count: int
    split_event_count: int
    dividend_event_count: int
    aggregate_structural_counts: tuple[tuple[str, int], ...]
    symbols: tuple[TiingoProfileRow, ...]

    @property
    def symbols_with_structural_anomalies(self) -> int:
        return sum(item.structural_anomaly_count > 0 for item in self.symbols)


def load_tiingo_profile_view(path: Path) -> TiingoProfileView:
    """Load and cross-check a derived Tiingo profile report."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TiingoProfileReportError(f"cannot read Tiingo profile: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TiingoProfileReportError("Tiingo profile is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TiingoProfileReportError("Tiingo profile root must be an object")
    if payload.get("schema_version") != "tiingo-durable-profile-v0.1":
        raise TiingoProfileReportError("unsupported Tiingo profile schema")

    generated_at = _required_text(payload.get("generated_at"), "generated_at")
    symbol_count = _nonnegative_int(payload.get("symbol_count"), "symbol_count")
    total_row_count = _nonnegative_int(payload.get("total_row_count"), "total_row_count")
    split_event_count = _nonnegative_int(payload.get("split_event_count"), "split_event_count")
    dividend_event_count = _nonnegative_int(
        payload.get("dividend_event_count"), "dividend_event_count"
    )
    aggregate = tuple(
        (field, _nonnegative_int(payload.get(field), field)) for field in _STRUCTURAL_FIELDS
    )

    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        raise TiingoProfileReportError("Tiingo profile symbols must be an array")
    rows: list[TiingoProfileRow] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            raise TiingoProfileReportError("Tiingo profile symbol entry must be an object")
        symbol = _required_text(raw.get("source_symbol"), "source_symbol")
        if symbol in seen:
            raise TiingoProfileReportError(f"duplicate Tiingo profile source symbol: {symbol}")
        seen.add(symbol)
        structural = sum(_nonnegative_int(raw.get(field), field) for field in _STRUCTURAL_FIELDS)
        rows.append(
            TiingoProfileRow(
                source_symbol=symbol,
                row_count=_nonnegative_int(raw.get("row_count"), "row_count"),
                first_date=_optional_text(raw.get("first_date"), "first_date"),
                last_date=_optional_text(raw.get("last_date"), "last_date"),
                split_event_count=_nonnegative_int(
                    raw.get("split_event_count"), "split_event_count"
                ),
                dividend_event_count=_nonnegative_int(
                    raw.get("dividend_event_count"), "dividend_event_count"
                ),
                structural_anomaly_count=structural,
            )
        )

    if symbol_count != len(rows):
        raise TiingoProfileReportError("Tiingo profile symbol_count does not match symbol entries")
    if total_row_count != sum(item.row_count for item in rows):
        raise TiingoProfileReportError("Tiingo profile total_row_count does not match symbol rows")
    if split_event_count != sum(item.split_event_count for item in rows):
        raise TiingoProfileReportError(
            "Tiingo profile split_event_count does not match symbol rows"
        )
    if dividend_event_count != sum(item.dividend_event_count for item in rows):
        raise TiingoProfileReportError(
            "Tiingo profile dividend_event_count does not match symbol rows"
        )

    return TiingoProfileView(
        generated_at=generated_at,
        symbol_count=symbol_count,
        total_row_count=total_row_count,
        split_event_count=split_event_count,
        dividend_event_count=dividend_event_count,
        aggregate_structural_counts=aggregate,
        symbols=tuple(sorted(rows, key=lambda item: item.source_symbol)),
    )


def render_tiingo_profile_html(view: TiingoProfileView) -> str:
    """Render a dependency-free private report from derived profile diagnostics."""

    shortest = tuple(
        sorted(view.symbols, key=lambda item: (item.row_count, item.source_symbol))[:15]
    )
    structural_rows = "".join(
        f"<tr><td>{escape(_label(field))}</td><td>{count}</td></tr>"
        for field, count in view.aggregate_structural_counts
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout Tiingo Profile</title>
<style>
:root{{color-scheme:dark;background:#11151b;color:#e7ebf0;font-family:system-ui,-apple-system,Segoe UI,sans-serif}}
body{{margin:0;padding:24px}} main{{max-width:1400px;margin:auto}} h1,h2{{margin:0 0 10px}} .sub{{color:#9aa6b2;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}} .card{{background:#18202a;border:1px solid #2b3745;border-radius:10px;padding:14px}}
.label{{font-size:12px;color:#9aa6b2;text-transform:uppercase;letter-spacing:.04em}} .metric{{font-size:28px;font-weight:700;margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:8px 10px;border-bottom:1px solid #2b3745;text-align:left;white-space:nowrap}} th{{color:#9aa6b2;position:sticky;top:0;background:#18202a}}
.section{{margin-top:24px}} .scroll{{overflow:auto;max-height:560px;border:1px solid #2b3745;border-radius:10px;background:#18202a}} .good{{color:#83d6a5}}
</style></head><body><main>
<h1>Tiingo durable-profile report</h1><div class="sub">Derived local evidence only. No raw OHLCV values are displayed. Generated {escape(view.generated_at)}.</div>
<div class="grid">
{_card("Profiled symbols", view.symbol_count)}{_card("Profiled rows", view.total_row_count)}{_card("Symbols with structural anomalies", view.symbols_with_structural_anomalies)}{_card("Split events", view.split_event_count)}{_card("Dividend events", view.dividend_event_count)}
</div>
<div class="section"><h2>Structural checks</h2><div class="card"><table><tbody>{structural_rows}</tbody></table></div></div>
<div class="section"><h2>Shortest observed histories</h2><div class="scroll"><table><thead>{_header()}</thead><tbody>{_rows(shortest)}</tbody></table></div></div>
<div class="section"><h2>All profiled symbols</h2><div class="scroll"><table><thead>{_header()}</thead><tbody>{_rows(view.symbols)}</tbody></table></div></div>
</main></body></html>"""


def _card(label: str, value: int) -> str:
    state = " good" if "anomal" in label.lower() and value == 0 else ""
    return f'<div class="card"><div class="label">{escape(label)}</div><div class="metric{state}">{value:,}</div></div>'


def _header() -> str:
    return "<tr><th>Symbol</th><th>Rows</th><th>First date</th><th>Last date</th><th>Splits</th><th>Dividends</th><th>Structural anomalies</th></tr>"


def _rows(rows: tuple[TiingoProfileRow, ...]) -> str:
    return "".join(
        "<tr>"
        f"<td><strong>{escape(item.source_symbol)}</strong></td>"
        f"<td>{item.row_count:,}</td>"
        f"<td>{escape(item.first_date or '—')}</td>"
        f"<td>{escape(item.last_date or '—')}</td>"
        f"<td>{item.split_event_count}</td>"
        f"<td>{item.dividend_event_count}</td>"
        f"<td>{item.structural_anomaly_count}</td>"
        "</tr>"
        for item in rows
    )


def _label(field: str) -> str:
    return field.removesuffix("_count").replace("_", " ").title()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TiingoProfileReportError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TiingoProfileReportError(f"{field} must be a non-negative integer")
    return value
