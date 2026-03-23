"""First concrete placement-level orchestration over an explicit seed order.

This module tries ordered provisional placement seeds, builds one initial
runtime routing snapshot per seed, and runs the existing one-snapshot route
orchestrator. It does not generate placements, mutate placements, reorder
requirements, retry alternate routes, backtrack, refine, or expand the grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from toolsv2.placement_solver import PlacementSeed
from toolsv2.route_orchestrator import OrchestrationResult
from toolsv2.solver_common import RouteRequirement, RouteRequirementSchemaView
from toolsv2.solver_runtime import PortGraphState


PlacementSetStatus = Literal["success", "failure_snapshot_set"]

RuntimeSnapshotBuilder = Callable[[PlacementSeed], PortGraphState]
OneSnapshotRouteOrchestrator = Callable[
    [PortGraphState, RouteRequirementSchemaView, tuple[RouteRequirement, ...]],
    OrchestrationResult,
]


@dataclass(frozen=True, slots=True)
class PlacementAttemptRecord:
    """One placement-seed attempt and its one-snapshot routing result."""

    placement_index: int
    placement_snapshot: PlacementSeed
    initial_runtime_state: PortGraphState
    route_orchestration_result: OrchestrationResult

    def __post_init__(self) -> None:
        if self.placement_index < 0:
            raise ValueError("PlacementAttemptRecord.placement_index must be non-negative")


@dataclass(frozen=True, slots=True)
class PlacementOrchestrationResult:
    """Result of trying an explicit ordered set of placement snapshots."""

    status: PlacementSetStatus
    placement_index: int | None = None
    placement_snapshot: PlacementSeed | None = None
    initial_runtime_state: PortGraphState | None = None
    final_state: PortGraphState | None = None
    route_orchestration_result: OrchestrationResult | None = None
    attempts: tuple[PlacementAttemptRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "success":
            if self.placement_index is None:
                raise ValueError("success PlacementOrchestrationResult requires placement_index")
            if self.placement_snapshot is None:
                raise ValueError("success PlacementOrchestrationResult requires placement_snapshot")
            if self.initial_runtime_state is None:
                raise ValueError("success PlacementOrchestrationResult requires initial_runtime_state")
            if self.final_state is None:
                raise ValueError("success PlacementOrchestrationResult requires final_state")
            if self.route_orchestration_result is None:
                raise ValueError("success PlacementOrchestrationResult requires route_orchestration_result")
            if self.route_orchestration_result.status != "success":
                raise ValueError(
                    "success PlacementOrchestrationResult requires successful route_orchestration_result"
                )
            if self.route_orchestration_result.final_state != self.final_state:
                raise ValueError(
                    "success PlacementOrchestrationResult final_state must match route_orchestration_result"
                )
            if self.attempts:
                raise ValueError("success PlacementOrchestrationResult must not include attempts")
            return

        if self.placement_index is not None:
            raise ValueError("failure_snapshot_set PlacementOrchestrationResult must not include placement_index")
        if self.placement_snapshot is not None:
            raise ValueError(
                "failure_snapshot_set PlacementOrchestrationResult must not include placement_snapshot"
            )
        if self.initial_runtime_state is not None:
            raise ValueError(
                "failure_snapshot_set PlacementOrchestrationResult must not include initial_runtime_state"
            )
        if self.final_state is not None:
            raise ValueError("failure_snapshot_set PlacementOrchestrationResult must not include final_state")
        if self.route_orchestration_result is not None:
            raise ValueError(
                "failure_snapshot_set PlacementOrchestrationResult must not include route_orchestration_result"
            )


@dataclass(frozen=True, slots=True)
class V1PlacementOrchestrator:
    """Thin placement-level orchestration over an explicit ordered seed set."""

    runtime_snapshot_builder: RuntimeSnapshotBuilder
    route_orchestrator: OneSnapshotRouteOrchestrator

    def __call__(
        self,
        placement_snapshots: tuple[PlacementSeed, ...],
        schema_view: RouteRequirementSchemaView,
        route_requirements: tuple[RouteRequirement, ...],
    ) -> PlacementOrchestrationResult:
        attempts: list[PlacementAttemptRecord] = []

        for placement_index, placement_snapshot in enumerate(placement_snapshots):
            if not isinstance(placement_snapshot, PlacementSeed):
                raise TypeError("placement_snapshots must contain PlacementSeed values")

            initial_runtime_state = self.runtime_snapshot_builder(placement_snapshot)
            route_orchestration_result = self.route_orchestrator(
                initial_runtime_state,
                schema_view,
                route_requirements,
            )
            if route_orchestration_result.status == "success":
                return PlacementOrchestrationResult(
                    status="success",
                    placement_index=placement_index,
                    placement_snapshot=placement_snapshot,
                    initial_runtime_state=initial_runtime_state,
                    final_state=route_orchestration_result.final_state,
                    route_orchestration_result=route_orchestration_result,
                )

            attempts.append(
                PlacementAttemptRecord(
                    placement_index=placement_index,
                    placement_snapshot=placement_snapshot,
                    initial_runtime_state=initial_runtime_state,
                    route_orchestration_result=route_orchestration_result,
                )
            )

        return PlacementOrchestrationResult(
            status="failure_snapshot_set",
            attempts=tuple(attempts),
        )


def build_v1_placement_orchestrator(
    runtime_snapshot_builder: RuntimeSnapshotBuilder,
    route_orchestrator: OneSnapshotRouteOrchestrator,
) -> V1PlacementOrchestrator:
    """Bind the builder and one-snapshot route orchestrator into the v1 layer."""

    return V1PlacementOrchestrator(
        runtime_snapshot_builder=runtime_snapshot_builder,
        route_orchestrator=route_orchestrator,
    )
