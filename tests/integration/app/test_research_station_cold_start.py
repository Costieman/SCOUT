from __future__ import annotations

import subprocess
import sys
import textwrap


COLD_START_BUDGET_SECONDS = 5.0
SUBPROCESS_TIMEOUT_SECONDS = 10.0


def test_research_station_runtime_configures_within_cold_start_budget(tmp_path) -> None:
    """Prevent expensive Brain inventory or analysis from re-entering startup."""

    experiment_root = tmp_path / "experiments"
    brain_root = tmp_path / "brains"
    experiment_root.mkdir()
    brain_root.mkdir()

    # A large irrelevant Brain inventory should not affect startup because v12 guidance is lazy.
    for index in range(1_000):
        (brain_root / f"brain-{index:04d}").mkdir()

    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from time import perf_counter

        started = perf_counter()
        from trade_scout.app.research_station_workflow_v12 import configure_research_station_runtime
        configure_research_station_runtime(
            experiment_root=Path({str(experiment_root)!r}),
            brain_root=Path({str(brain_root)!r}),
        )
        print(perf_counter() - started)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    elapsed = float(completed.stdout.strip().splitlines()[-1])

    assert elapsed < COLD_START_BUDGET_SECONDS, (
        f"Research Station cold start took {elapsed:.2f}s; "
        f"budget is {COLD_START_BUDGET_SECONDS:.2f}s"
    )
