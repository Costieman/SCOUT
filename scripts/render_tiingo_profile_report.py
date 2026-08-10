"""Render a private HTML report from derived Tiingo profile evidence."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from trade_scout.app.tiingo_profile_report import (
    TiingoProfileReportError,
    load_tiingo_profile_view,
    render_tiingo_profile_html,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    profile = root / "evidence" / "tiingo-profile" / "profile.json"
    output = root / "evidence" / "tiingo-profile" / "report.html"
    try:
        view = load_tiingo_profile_view(profile)
    except TiingoProfileReportError as exc:
        raise SystemExit(f"Tiingo profile report error: {exc}") from exc

    output.write_text(render_tiingo_profile_html(view), encoding="utf-8")
    print(output)
    if args.open_browser:
        webbrowser.open(output.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
