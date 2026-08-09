from pathlib import Path


def test_daily_update_evidence_cli_is_narrow_operational_entry_point() -> None:
    script = Path("scripts/write_eodhd_daily_update_evidence.py").read_text(encoding="utf-8")

    assert "This does not perform provider calls" in script
    assert "assess_eodhd_daily_update" in script
    assert "write_eodhd_daily_update_report" in script
