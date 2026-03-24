"""Full multi-grid solve orchestration above the current-grid solve shell.

This module owns only the explicit ordered retry loop across active-grid
snapshots. It does not perform placement search, route search, commit logic,
refinement, rendering, or hidden grid-expansion heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

from toolsv2.graph_content import GraphContentModel
from toolsv2.grid_expansion_policy import GridExpansionPolicy
from toolsv2.layout_estimation import LayoutDemandEstimate, LayoutDemandEstimator
from toolsv2.layout_profiles import LayoutProfile
from toolsv2.profile import build_minimum_active_grid
from toolsv2.solve_pipeline import (
    CurrentGridSolveResult,
    build_v1_current_grid_solve_pipeline,
    build_v1_current_grid_solve_pipeline_for_layout_profile,
)
from toolsv2.solver_common import ActiveGridState, LogicalXRailId, LogicalYRailId
from toolsv2.solver_runtime import PortGraphState


FullSolveStatus = Literal["success", "failure_grid_set"]
CurrentGridSolver = Callable[[ActiveGridState, GraphContentModel], CurrentGridSolveResult]
GridExpansionPolicyBuilder = Callable[[LayoutDemandEstimate], GridExpansionPolicy]


@dataclass(frozen=True, slots=True)
class GridSolveAttemptRecord:
    """One explicit current-grid solve attempt."""

    attempt_index: int
    active_grid: ActiveGridState
    current_grid_result: CurrentGridSolveResult

    def __post_init__(self) -> None:
        if self.attempt_index < 0:
            raise ValueError("GridSolveAttemptRecord.attempt_index must be non-negative")
        if self.current_grid_result.active_grid != self.active_grid:
            raise ValueError(
                "GridSolveAttemptRecord.active_grid must match current_grid_result.active_grid"
            )


@dataclass(frozen=True, slots=True)
class FullSolveResult:
    """Result of trying an explicit ordered set of active-grid snapshots."""

    status: FullSolveStatus
    initial_grid: ActiveGridState
    attempts: tuple[GridSolveAttemptRecord, ...]
    final_grid: ActiveGridState | None = None
    final_state: PortGraphState | None = None
    successful_current_grid_result: CurrentGridSolveResult | None = None

    def __post_init__(self) -> None:
        if not self.attempts:
            raise ValueError("FullSolveResult.attempts must not be empty")

        if self.status == "success":
            if self.final_grid is None:
                raise ValueError("success FullSolveResult requires final_grid")
            if self.final_state is None:
                raise ValueError("success FullSolveResult requires final_state")
            if self.successful_current_grid_result is None:
                raise ValueError(
                    "success FullSolveResult requires successful_current_grid_result"
                )
            if self.successful_current_grid_result.status != "success":
                raise ValueError(
                    "success FullSolveResult requires a successful current-grid result"
                )
            if self.successful_current_grid_result.active_grid != self.final_grid:
                raise ValueError(
                    "success FullSolveResult final_grid must match successful current-grid result"
                )
            if self.successful_current_grid_result.final_state != self.final_state:
                raise ValueError(
                    "success FullSolveResult final_state must match successful current-grid result"
                )
            if self.attempts[-1].current_grid_result != self.successful_current_grid_result:
                raise ValueError(
                    "success FullSolveResult last attempt must be the successful current-grid result"
                )
            return

        if self.final_grid is not None:
            raise ValueError("failure_grid_set FullSolveResult must not include final_grid")
        if self.final_state is not None:
            raise ValueError("failure_grid_set FullSolveResult must not include final_state")
        if self.successful_current_grid_result is not None:
            raise ValueError(
                "failure_grid_set FullSolveResult must not include successful_current_grid_result"
            )


def _run_full_solve_loop(
    *,
    initial_grid: ActiveGridState,
    content: GraphContentModel,
    grid_expansion_policy: GridExpansionPolicy,
    current_grid_solver: CurrentGridSolver,
    max_grid_attempts: int | None,
) -> FullSolveResult:
    attempts: list[GridSolveAttemptRecord] = []
    current_grid = initial_grid
    seen_grids = {current_grid}
    attempt_index = 0

    while True:
        if max_grid_attempts is not None and attempt_index >= max_grid_attempts:
            return FullSolveResult(
                status="failure_grid_set",
                initial_grid=initial_grid,
                attempts=tuple(attempts),
            )

        current_grid_result = current_grid_solver(current_grid, content)
        attempts.append(
            GridSolveAttemptRecord(
                attempt_index=attempt_index,
                active_grid=current_grid,
                current_grid_result=current_grid_result,
            )
        )
        if current_grid_result.status == "success":
            return FullSolveResult(
                status="success",
                initial_grid=initial_grid,
                attempts=tuple(attempts),
                final_grid=current_grid,
                final_state=current_grid_result.final_state,
                successful_current_grid_result=current_grid_result,
            )

        next_grid = grid_expansion_policy(current_grid)
        if next_grid is None:
            return FullSolveResult(
                status="failure_grid_set",
                initial_grid=initial_grid,
                attempts=tuple(attempts),
            )
        if next_grid == current_grid:
            raise ValueError("grid_expansion_policy must not return the same grid")
        if next_grid in seen_grids:
            raise ValueError("grid_expansion_policy must not cycle to an already tried grid")

        current_grid = next_grid
        seen_grids.add(current_grid)
        attempt_index += 1


@dataclass(frozen=True, slots=True)
class V1FullSolveOrchestrator:
    """Thin full solve loop over explicit active-grid expansions."""

    default_x_rail_ids: tuple[LogicalXRailId, ...]
    authored_tier_rail_ids: tuple[LogicalYRailId, ...]
    grid_expansion_policy: GridExpansionPolicy
    current_grid_solver: CurrentGridSolver
    max_grid_attempts: int | None = None

    def __post_init__(self) -> None:
        if not self.default_x_rail_ids:
            raise ValueError("default_x_rail_ids must not be empty")
        if not self.authored_tier_rail_ids:
            raise ValueError("authored_tier_rail_ids must not be empty")
        if self.max_grid_attempts is not None and self.max_grid_attempts < 1:
            raise ValueError("max_grid_attempts must be at least 1 when set")

    def __call__(self, content: GraphContentModel) -> FullSolveResult:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=self.default_x_rail_ids,
            authored_tier_rail_ids=self.authored_tier_rail_ids,
        )
        return _run_full_solve_loop(
            initial_grid=initial_grid,
            content=content,
            grid_expansion_policy=self.grid_expansion_policy,
            current_grid_solver=self.current_grid_solver,
            max_grid_attempts=self.max_grid_attempts,
        )


@dataclass(frozen=True, slots=True)
class V1EstimatedFullSolveOrchestrator:
    """Thin full solve loop with a reusable content-driven initial-grid estimate."""

    layout_demand_estimator: LayoutDemandEstimator
    grid_expansion_policy_builder: GridExpansionPolicyBuilder
    current_grid_solver: CurrentGridSolver
    max_grid_attempts: int | None = None

    def __post_init__(self) -> None:
        if self.max_grid_attempts is not None and self.max_grid_attempts < 1:
            raise ValueError("max_grid_attempts must be at least 1 when set")

    def __call__(self, content: GraphContentModel) -> FullSolveResult:
        estimate = self.layout_demand_estimator(content)
        return _run_full_solve_loop(
            initial_grid=estimate.initial_grid,
            content=content,
            grid_expansion_policy=self.grid_expansion_policy_builder(estimate),
            current_grid_solver=self.current_grid_solver,
            max_grid_attempts=self.max_grid_attempts,
        )


def build_v1_full_solve_orchestrator(
    default_x_rail_ids: Sequence[str | LogicalXRailId],
    authored_tier_rail_ids: Sequence[str | LogicalYRailId],
    grid_expansion_policy: GridExpansionPolicy,
    max_placement_seeds: int = 1,
    max_grid_attempts: int | None = None,
    minimum_same_row_gap: int = 1,
    current_grid_solver: CurrentGridSolver | None = None,
) -> V1FullSolveOrchestrator:
    """Bind the current-grid shell into a full explicit multi-grid loop."""

    if current_grid_solver is None:
        current_grid_solver = build_v1_current_grid_solve_pipeline(
            max_placement_seeds=max_placement_seeds,
            minimum_same_row_gap=minimum_same_row_gap,
        )

    return V1FullSolveOrchestrator(
        default_x_rail_ids=tuple(LogicalXRailId(str(rail_id)) for rail_id in default_x_rail_ids),
        authored_tier_rail_ids=tuple(
            LogicalYRailId(str(rail_id))
            for rail_id in authored_tier_rail_ids
        ),
        grid_expansion_policy=grid_expansion_policy,
        current_grid_solver=current_grid_solver,
        max_grid_attempts=max_grid_attempts,
    )


def build_v1_full_solve_orchestrator_for_layout_profile(
    layout_profile: LayoutProfile,
    authored_tier_rail_ids: Sequence[str | LogicalYRailId],
    grid_expansion_policy: GridExpansionPolicy,
    max_placement_seeds: int = 1,
    max_grid_attempts: int | None = None,
    current_grid_solver: CurrentGridSolver | None = None,
) -> V1FullSolveOrchestrator:
    """Bind the full explicit multi-grid loop from one explicit layout profile."""

    if current_grid_solver is None:
        current_grid_solver = build_v1_current_grid_solve_pipeline_for_layout_profile(
            layout_profile=layout_profile,
            max_placement_seeds=max_placement_seeds,
        )

    return V1FullSolveOrchestrator(
        default_x_rail_ids=layout_profile.default_x_rail_ids,
        authored_tier_rail_ids=tuple(
            LogicalYRailId(str(rail_id))
            for rail_id in authored_tier_rail_ids
        ),
        grid_expansion_policy=grid_expansion_policy,
        current_grid_solver=current_grid_solver,
        max_grid_attempts=max_grid_attempts,
    )


def build_v1_estimated_full_solve_orchestrator(
    layout_demand_estimator: LayoutDemandEstimator,
    grid_expansion_policy_builder: GridExpansionPolicyBuilder,
    max_placement_seeds: int = 1,
    max_grid_attempts: int | None = None,
    minimum_same_row_gap: int = 1,
    current_grid_solver: CurrentGridSolver | None = None,
) -> V1EstimatedFullSolveOrchestrator:
    """Bind the full solve loop from a reusable content-driven layout estimate."""

    if current_grid_solver is None:
        current_grid_solver = build_v1_current_grid_solve_pipeline(
            max_placement_seeds=max_placement_seeds,
            minimum_same_row_gap=minimum_same_row_gap,
        )

    return V1EstimatedFullSolveOrchestrator(
        layout_demand_estimator=layout_demand_estimator,
        grid_expansion_policy_builder=grid_expansion_policy_builder,
        current_grid_solver=current_grid_solver,
        max_grid_attempts=max_grid_attempts,
    )
