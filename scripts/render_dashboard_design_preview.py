"""Render the synthetic dashboard architecture preview without provider or workspace access."""

from __future__ import annotations

import argparse
from pathlib import Path

from trade_scout.app.dashboard_design_preview import render_dashboard_design_preview


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the synthetic Trade Scout dashboard blueprint."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/dashboard-design-preview/index.html"),
    )
    args = parser.parse_args()

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard_design_preview(), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
