# ruff: noqa: E501
"""Small SVG chart renderer for Strategy Builder entry-parameter sweeps."""

from __future__ import annotations

from html import escape
from typing import cast

from trade_scout.app.strategy_builder_entry_sweep import StrategyBuilderEntrySweepReport


def render_entry_sweep_chart(report: StrategyBuilderEntrySweepReport) -> str:
    """Render hold expectancy over the declared entry-parameter range."""

    points = tuple(item for item in report.points if item.expectancy is not None)
    if not points:
        return '<div class="section-note">No complete outcomes are available for this sweep.</div>'

    width, height = 920.0, 310.0
    left, right, top, bottom = 72.0, 28.0, 28.0, 58.0
    x_min = min(item.value for item in points)
    x_max = max(item.value for item in points)
    values = tuple(cast(float, item.expectancy) * 100.0 for item in points)
    y_min, y_max = min(values), max(values)
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5
    padding = max((y_max - y_min) * 0.12, 0.05)
    y_min -= padding
    y_max += padding

    def x(value: float) -> float:
        fraction = 0.5 if x_max == x_min else (value - x_min) / (x_max - x_min)
        return left + fraction * (width - left - right)

    def y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * (height - top - bottom)

    polyline = " ".join(
        f"{x(item.value):.1f},{y(cast(float, item.expectancy) * 100.0):.1f}" for item in points
    )
    circles = "".join(
        f'<circle cx="{x(item.value):.1f}" cy="{y(cast(float, item.expectancy) * 100.0):.1f}" r="4.5" fill="#f1c84b"><title>{item.value:g} {escape(report.unit_label)}: {_pct(item.expectancy)}, complete N={item.complete_event_count}</title></circle>'
        for item in points
    )
    label = escape(report.parameter_label)
    unit = escape(report.unit_label)
    return f"""<svg viewBox="0 0 {width:g} {height:g}" role="img" aria-label="Hold expectancy across {label} sweep" style="width:100%;min-height:280px;background:#10151d;border:1px solid #293241;border-radius:10px">
<line x1="{left:g}" x2="{left:g}" y1="{top:g}" y2="{height - bottom:g}" stroke="#657184"/>
<line x1="{left:g}" x2="{width - right:g}" y1="{height - bottom:g}" y2="{height - bottom:g}" stroke="#657184"/>
<polyline points="{polyline}" fill="none" stroke="#f1c84b" stroke-width="3"/>{circles}
<text x="{left:g}" y="{height - 20:g}" fill="#98a6b8" font-size="11">{x_min:g}</text>
<text x="{width - right:g}" y="{height - 20:g}" text-anchor="end" fill="#98a6b8" font-size="11">{x_max:g}</text>
<text x="{(left + width - right) / 2:g}" y="{height - 20:g}" text-anchor="middle" fill="#edf1f7" font-size="12">{label} ({unit})</text>
<text transform="translate(18 {(top + height - bottom) / 2:g}) rotate(-90)" text-anchor="middle" fill="#edf1f7" font-size="12">Hold expectancy per trade (%)</text>
</svg>"""


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


__all__ = ["render_entry_sweep_chart"]
