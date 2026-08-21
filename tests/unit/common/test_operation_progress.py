from trade_scout.common.operation_progress import (
    OperationFailure,
    OperationProgressEvent,
    OperationState,
)


def test_failed_event_requires_machine_readable_failure() -> None:
    try:
        OperationProgressEvent(
            operation_id="import-1",
            operation_type="import",
            stage="identity",
            state=OperationState.FAILED,
            completed=12,
            total=503,
            elapsed_seconds=4.0,
        )
    except ValueError as exc:
        assert "require failure metadata" in str(exc)
    else:
        raise AssertionError("FAILED progress without failure metadata must be rejected")


def test_failure_is_localised_to_same_stage_and_asset() -> None:
    failure = OperationFailure(
        code="IDENTITY_AMBIGUOUS_SYMBOL",
        message="provider symbol resolves to multiple canonical candidates",
        stage="identity",
        asset_or_parameter="BRK.B",
        retryable=False,
    )
    event = OperationProgressEvent(
        operation_id="import-1",
        operation_type="import",
        stage="identity",
        state=OperationState.FAILED,
        completed=12,
        total=503,
        elapsed_seconds=4.0,
        asset_or_parameter="BRK.B",
        failure=failure,
    )
    assert event.failure is not None
    assert event.failure.code == "IDENTITY_AMBIGUOUS_SYMBOL"
    assert event.asset_or_parameter == "BRK.B"


def test_progress_rejects_impossible_counts() -> None:
    try:
        OperationProgressEvent(
            operation_id="research-1",
            operation_type="research",
            stage="events",
            state=OperationState.RUNNING,
            completed=11,
            total=10,
            elapsed_seconds=1.0,
        )
    except ValueError as exc:
        assert "completed cannot exceed total" in str(exc)
    else:
        raise AssertionError("impossible progress must be rejected")


def test_waiting_event_can_expose_rate_limit_delay() -> None:
    event = OperationProgressEvent(
        operation_id="import-1",
        operation_type="import",
        stage="acquisition",
        state=OperationState.WAITING,
        completed=474,
        total=503,
        elapsed_seconds=900.0,
        asset_or_parameter="provider-rate-limit",
        wait_seconds=900.0,
        retry_count=6,
    )
    assert event.wait_seconds == 900.0
    assert event.retry_count == 6
