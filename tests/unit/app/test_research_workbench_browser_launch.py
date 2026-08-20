from pathlib import Path


def test_workbench_waits_for_listener_before_opening_browser() -> None:
    source = Path("scripts/serve_research_workbench.py").read_text(encoding="utf-8")
    assert "_open_browser_when_ready" in source
    assert "socket.create_connection" in source
    assert "Thread(" in source
