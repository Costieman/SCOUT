from types import SimpleNamespace

from trade_scout.app import research_station_workflow_v12 as workflow
from trade_scout.experiments.contracts import ExperimentStatus


def _membership(*, experiment_id: str, checksum: str) -> SimpleNamespace:
    return SimpleNamespace(
        membership_id=f"membership-{experiment_id}",
        experiment_id=experiment_id,
        experiment_manifest_checksum=checksum,
        experiment_status=ExperimentStatus.SUCCEEDED,
    )


def test_membership_fingerprint_is_order_independent() -> None:
    first = _membership(experiment_id="exp-a", checksum="aaa")
    second = _membership(experiment_id="exp-b", checksum="bbb")

    assert workflow._membership_fingerprint((first, second)) == workflow._membership_fingerprint(
        (second, first)
    )


def test_membership_fingerprint_changes_when_brain_membership_changes() -> None:
    first = _membership(experiment_id="exp-a", checksum="aaa")
    changed = _membership(experiment_id="exp-b", checksum="bbb")

    assert workflow._membership_fingerprint((first,)) != workflow._membership_fingerprint(
        (first, changed)
    )


def test_v12_uses_on_demand_guidance_instead_of_startup_indexing() -> None:
    source = workflow.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()

    assert "trade-scout:on-demand-brain-guidance-v12" in text
    assert "/research/brain-guidance" in text
    assert "fetch(`/research/brain-guidance?brain=" in text
    assert "Thread(" not in text
    assert "list_brains()" not in text
