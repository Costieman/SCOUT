from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign_suite import (
    EodhdCampaignSuiteCase,
    EodhdCampaignSuiteError,
    EodhdCampaignSuiteExecutionError,
    run_eodhd_campaign_suite,
)


def _cases() -> tuple[EodhdCampaignSuiteCase, ...]:
    return (
        EodhdCampaignSuiteCase(
            case_id="active-split",
            symbol="AAA.US",
            start=date(2020, 1, 1),
            end=date(2020, 12, 31),
            expected_active=True,
            dataset_version=DatasetVersion("eodhd-active-split-v1"),
        ),
        EodhdCampaignSuiteCase(
            case_id="delisted-history",
            symbol="OLD.US",
            start=date(2018, 1, 1),
            end=date(2020, 12, 31),
            expected_active=False,
            dataset_version=DatasetVersion("eodhd-delisted-history-v1"),
        ),
    )


def _result_for_case(case: EodhdCampaignSuiteCase) -> dict[str, object]:
    return {"case_id": case.case_id}


def test_suite_runs_each_case_once_and_resumes_without_repeating(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner(case: EodhdCampaignSuiteCase) -> dict[str, object]:
        calls.append(case.case_id)
        return {"case_id": case.case_id, "passed": True}

    first = run_eodhd_campaign_suite(_cases(), root=tmp_path, case_runner=runner)
    second = run_eodhd_campaign_suite(_cases(), root=tmp_path, case_runner=runner)

    assert first.complete is True
    assert second.complete is True
    assert calls == ["active-split", "delisted-history"]
    assert first.completed_case_ids == ("active-split", "delisted-history")


def test_failure_preserves_prior_completed_case_and_resumes_from_failure(tmp_path: Path) -> None:
    calls: list[str] = []
    fail = True

    def runner(case: EodhdCampaignSuiteCase) -> dict[str, object]:
        nonlocal fail
        calls.append(case.case_id)
        if case.case_id == "delisted-history" and fail:
            fail = False
            raise RuntimeError("provider unavailable")
        return {"case_id": case.case_id, "passed": True}

    with pytest.raises(EodhdCampaignSuiteExecutionError, match="delisted-history"):
        run_eodhd_campaign_suite(_cases(), root=tmp_path, case_runner=runner)

    resumed = run_eodhd_campaign_suite(_cases(), root=tmp_path, case_runner=runner)

    assert resumed.complete is True
    assert calls == ["active-split", "delisted-history", "delisted-history"]


def test_changed_campaign_configuration_creates_distinct_campaign_identity(tmp_path: Path) -> None:
    first = run_eodhd_campaign_suite(_cases(), root=tmp_path, case_runner=_result_for_case)
    changed = list(_cases())
    changed[0] = EodhdCampaignSuiteCase(
        case_id="active-split",
        symbol="AAA.US",
        start=date(2019, 1, 1),
        end=date(2020, 12, 31),
        expected_active=True,
        dataset_version=DatasetVersion("eodhd-active-split-v1"),
    )

    second = run_eodhd_campaign_suite(
        tuple(changed),
        root=tmp_path,
        case_runner=_result_for_case,
    )

    assert first.campaign_id != second.campaign_id


def test_duplicate_case_or_dataset_identity_fails_closed(tmp_path: Path) -> None:
    cases = _cases()
    duplicate_case = (cases[0], cases[0])
    with pytest.raises(EodhdCampaignSuiteError, match="case IDs"):
        run_eodhd_campaign_suite(
            duplicate_case,
            root=tmp_path,
            case_runner=_result_for_case,
        )

    duplicate_dataset = (
        cases[0],
        EodhdCampaignSuiteCase(
            case_id="other",
            symbol="BBB.US",
            start=date(2020, 1, 1),
            end=date(2020, 2, 1),
            expected_active=True,
            dataset_version=cases[0].dataset_version,
        ),
    )
    with pytest.raises(EodhdCampaignSuiteError, match="dataset versions"):
        run_eodhd_campaign_suite(
            duplicate_dataset,
            root=tmp_path,
            case_runner=_result_for_case,
        )


def test_checkpoint_cannot_claim_missing_result(tmp_path: Path) -> None:
    cases = _cases()
    result = run_eodhd_campaign_suite(
        cases,
        root=tmp_path,
        case_runner=_result_for_case,
    )
    result_path = tmp_path / result.campaign_id / "cases" / cases[0].case_id / "result.json"
    result_path.unlink()

    with pytest.raises(EodhdCampaignSuiteError, match="result is missing"):
        run_eodhd_campaign_suite(
            cases,
            root=tmp_path,
            case_runner=_result_for_case,
        )
