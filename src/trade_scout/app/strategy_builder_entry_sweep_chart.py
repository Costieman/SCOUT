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

    width, height = 920.0, 340.0
    left, right, top, bottom = 78.0, 34.0, 34.0, 72.0
    x_min = min(item.value for item in points)
    x_max = max(item.value for item in points)
    values = tuple(cast(float, item.expectancy) * 100.0 for item in points)
    y_min, y_max = min(values), max(values)
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5
    padding = max((y_max - y_min) * 0.18, 0.08)
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
        f'<circle cx="{x(item.value):.1f}" cy="{y(cast(float, item.expectancy) * 100.0):.1f}" r="5" fill="#f1c84b"><title>{item.value:g} {escape(report.unit_label)}: {_pct(item.expectancy)}, complete N={item.complete_event_count}</title></circle>'
        for item in points
    )
    point_labels = "".join(
        f'<text x="{x(item.value):.1f}" y="{y(cast(float, item.expectancy) * 100.0) - 10:.1f}" text-anchor="middle" fill="#dce5ef" font-size="11">{_pct(item.expectancy)}</text>'
        for item in points
    )
    x_ticks = "".join(
        f'<line class="entry-sweep-axis" x1="{x(item.value):.1f}" x2="{x(item.value):.1f}" y1="{height - bottom:g}" y2="{height - bottom + 5:g}" stroke="#657184"/><text x="{x(item.value):.1f}" y="{height - bottom + 22:g}" text-anchor="middle" fill="#c8d1dc" font-size="11">{item.value:g}</text>'
        for item in points
    )
    y_ticks: list[str] = []
    for index in range(5):
        value = y_min + (y_max - y_min) * index / 4.0
        y_pos = y(value)
        y_ticks.append(
            f'<line class="entry-sweep-grid" x1="{left:g}" x2="{width - right:g}" y1="{y_pos:.1f}" y2="{y_pos:.1f}" stroke="#354052" stroke-width="1" opacity=".65"/>'
            f'<text x="{left - 10:g}" y="{y_pos + 4:.1f}" text-anchor="end" fill="#c8d1dc" font-size="11">{value:+.2f}%</text>'
        )
    label = escape(report.parameter_label)
    unit = escape(report.unit_label)
    return f"""<svg viewBox="0 0 {width:g} {height:g}" role="img" aria-label="Hold expectancy across {label} sweep" style="width:100%;min-height:300px;background:#10151d;border:1px solid #293241;border-radius:10px">
{"".join(y_ticks)}
<line class="entry-sweep-axis" x1="{left:g}" x2="{left:g}" y1="{top:g}" y2="{height - bottom:g}" stroke="#657184" stroke-width="1.4"/>
<line class="entry-sweep-axis" x1="{left:g}" x2="{width - right:g}" y1="{height - bottom:g}" y2="{height - bottom:g}" stroke="#657184" stroke-width="1.4"/>
{x_ticks}
<polyline points="{polyline}" fill="none" stroke="#f1c84b" stroke-width="3"/>{circles}{point_labels}
<text x="{(left + width - right) / 2:g}" y="{height - 18:g}" text-anchor="middle" fill="#edf1f7" font-size="12">{label} ({unit})</text>
<text transform="translate(18 {(top + height - bottom) / 2:g}) rotate(-90)" text-anchor="middle" fill="#edf1f7" font-size="12">Hold expectancy per trade (%)</text>
</svg>"""


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


__all__ = ["render_entry_sweep_chart"]
