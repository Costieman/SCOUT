"""Bounded parallel execution for independent asset-level SCOUT work."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class AssetExecutionResult(Generic[T, R]):
    asset: T
    value: R | None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error_type is None


def execute_assets_bounded(
    assets: Iterable[T],
    worker: Callable[[T], R],
    *,
    max_workers: int = 4,
) -> tuple[AssetExecutionResult[T, R], ...]:
    """Execute independent assets with bounded concurrency and localized failures.

    Results are returned in input order. One asset failure never hides the identity of the
    failing unit and does not cancel already-independent work for other assets.
    """

    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    materialized = tuple(assets)
    if not materialized:
        return ()

    indexed: dict[int, AssetExecutionResult[T, R]] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(materialized))) as pool:
        future_to_index = {
            pool.submit(worker, asset): index for index, asset in enumerate(materialized)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            asset = materialized[index]
            try:
                indexed[index] = AssetExecutionResult(asset=asset, value=future.result())
            except Exception as exc:  # callers decide retry/quarantine policy from localized result
                indexed[index] = AssetExecutionResult(
                    asset=asset,
                    value=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
    return tuple(indexed[index] for index in range(len(materialized)))


__all__ = ["AssetExecutionResult", "execute_assets_bounded"]
