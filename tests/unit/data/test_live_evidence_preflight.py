from pathlib import Path

from trade_scout.data.live_evidence_preflight import assess_live_evidence_preflight


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_preflight_requires_primary_credentials_and_checked_in_controls(tmp_path: Path) -> None:
    policy = _touch(tmp_path / "policy.json")
    provider = _touch(tmp_path / "provider.json")
    data = _touch(tmp_path / "data.json")
    plan = tmp_path / "plan.json"

    report = assess_live_evidence_preflight(
        environment={"EODHD_API_KEY": "token"},
        representative_policy=policy,
        provider_ledger=provider,
        data_ledger=data,
        representative_plan=plan,
    )

    assert report.primary_ready is True
    assert report.secondary_ready is False
    assert report.blockers == ()
    assert report.notes == (
        "representative plan is absent and will be created from live EODHD inventory",
        "TIINGO_API_KEY is absent; secondary validation will remain outstanding",
    )


def test_preflight_fails_closed_on_missing_primary_prerequisites(tmp_path: Path) -> None:
    report = assess_live_evidence_preflight(
        environment={"TIINGO_API_KEY": "secondary"},
        representative_policy=tmp_path / "missing-policy.json",
        provider_ledger=tmp_path / "missing-provider.json",
        data_ledger=tmp_path / "missing-data.json",
        representative_plan=tmp_path / "missing-plan.json",
    )

    assert report.primary_ready is False
    assert report.secondary_ready is False
    assert report.blockers == (
        "EODHD_API_TOKEN or EODHD_API_KEY is not configured",
        "representative storage policy is missing",
        "EODHD provider-acceptance ledger is missing",
        "data-foundation acceptance ledger is missing",
    )


def test_preflight_accepts_eodhd_api_token_and_tiingo_for_secondary(tmp_path: Path) -> None:
    report = assess_live_evidence_preflight(
        environment={"EODHD_API_TOKEN": "primary", "TIINGO_API_KEY": "secondary"},
        representative_policy=_touch(tmp_path / "policy.json"),
        provider_ledger=_touch(tmp_path / "provider.json"),
        data_ledger=_touch(tmp_path / "data.json"),
        representative_plan=_touch(tmp_path / "plan.json"),
    )

    assert report.primary_ready is True
    assert report.secondary_ready is True
    assert report.plan_present is True
    assert report.blockers == ()
    assert report.notes == ()
