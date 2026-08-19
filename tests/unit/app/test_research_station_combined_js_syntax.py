from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from trade_scout.app import research_station_workflow_v5 as workflow
from trade_scout.app import research_workbench_console as console


def test_combined_research_station_asset_is_valid_javascript(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available for JavaScript syntax validation")

    workflow.configure_research_station_runtime()
    asset_path = tmp_path / "strategy-builder-research-memory.js"
    asset_path.write_text(console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS, encoding="utf-8")

    completed = subprocess.run(
        [node, "--check", str(asset_path)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
