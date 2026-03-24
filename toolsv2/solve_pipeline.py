"""Thin current-grid solve shell over the existing logical stack.

This module binds the current explicit graph-content boundary to the existing:

- production definitions/content loader
- pass-1 placement search on one active grid
- placement-seed routing orchestration on that same active grid

It intentionally does not implement:

- grid expansion
- refinement
- renderer behavior
- alternate routing/placement policy beyond the already-frozen lower layers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from toolsv2.adjacency import build_v1_junction_adjacency_finder
from toolsv2.definitions_loader import LoadedGraphContent, load_v1_graph_content
from toolsv2.eligibility import build_v1_candidate_eligibility
from toolsv2.geometry import build_v1_junction_geometry_build_feasibility
from toolsv2.graph_content import GraphContentModel
from toolsv2.placement_orchestrator import (
    PlacementOrchestrationResult,
    build_v1_placement_orchestrator,
)
from toolsv2.placement_solver import PlacementResult, solve_placement_on_current_grid
from toolsv2.route_commit import V1RouteCommit
from toolsv2.route_orchestrator import build_v1_route_orchestrator
from toolsv2.router import build_v1_router
from toolsv2.runtime_snapshot_builder import build_v1_runtime_snapshot_builder
from toolsv2.solver_common import ActiveGridState
from toolsv2.solver_runtime import PortGraphState
from toolsv2.layout_profiles import LayoutProfile


SolveStatus = Literal[
    "success",
    "placement_failure_on_current_grid",
    "routing_failure_on_current_grid",
]


@dataclass(frozen=True, slots=True)
class CurrentGridSolveResult:
    """Result of solving explicit graph content on one fixed active grid only."""

    status: SolveStatus
    active_grid: ActiveGridState
    loaded_content: LoadedGraphContent
    placement_result: PlacementResult
    placement_orchestration_result: PlacementOrchestrationResult | None = None
    final_state: PortGraphState | None = None

    def __post_init__(self) -> None:
        if self.status == "success":
            if self.placement_result.status != "success":
                raise ValueError("success CurrentGridSolveResult requires successful placement_result")
            if self.placement_orchestration_result is None:
                raise ValueError(
                    "success CurrentGridSolveResult requires placement_orchestration_result"
                )
            if self.placement_orchestration_result.status != "success":
                raise ValueError(
                    "success CurrentGridSolveResult requires successful placement_orchestration_result"
                )
            if self.final_state is None:
                raise ValueError("success CurrentGridSolveResult requires final_state")
            if self.placement_orchestration_result.final_state != self.final_state:
                raise ValueError(
                    "success CurrentGridSolveResult final_state must match placement_orchestration_result"
                )
            return

        if self.status == "placement_failure_on_current_grid":
            if self.placement_result.status != "failure_on_current_grid":
                raise ValueError(
                    "placement_failure_on_current_grid requires failed placement_result"
                )
            if self.placement_orchestration_result is not None:
                raise ValueError(
                    "placement_failure_on_current_grid must not include placement_orchestration_result"
                )
            if self.final_state is not None:
                raise ValueError(
                    "placement_failure_on_current_grid must not include final_state"
                )
            return

        if self.placement_result.status != "success":
            raise ValueError(
                "routing_failure_on_current_grid requires successful placement_result"
            )
        if self.placement_orchestration_result is None:
            raise ValueError(
                "routing_failure_on_current_grid requires placement_orchestration_result"
            )
        if self.placement_orchestration_result.status != "failure_snapshot_set":
            raise ValueError(
                "routing_failure_on_current_grid requires failed placement_orchestration_result"
            )
        if self.final_state is not None:
            raise ValueError("routing_failure_on_current_grid must not include final_state")


@dataclass(frozen=True, slots=True)
class V1CurrentGridSolvePipeline:
    """Thin current-grid solve shell over the implemented logical stack."""

    max_placement_seeds: int = 1
    minimum_same_row_gap: int = 1

    def __post_init__(self) -> None:
        if self.max_placement_seeds < 1:
            raise ValueError("max_placement_seeds must be at least 1")
        if self.minimum_same_row_gap < 0:
            raise ValueError("minimum_same_row_gap must be non-negative")

    def __call__(
        self,
        active_grid: ActiveGridState,
        content: GraphContentModel,
    ) -> CurrentGridSolveResult:
        loaded_content = load_v1_graph_content(content)
        placement_result = solve_placement_on_current_grid(
            active_grid=active_grid,
            routing_policy=loaded_content.routing_policy,
            node_definitions=loaded_content.node_definitions,
            node_metadata=loaded_content.node_metadata,
            ordered_same_row_groups=loaded_content.ordered_same_row_groups,
            port_requirements_by_node_id=loaded_content.port_requirements_by_node_id,
            max_seeds=self.max_placement_seeds,
            minimum_same_row_gap=self.minimum_same_row_gap,
        )
        if placement_result.status != "success":
            return CurrentGridSolveResult(
                status="placement_failure_on_current_grid",
                active_grid=active_grid,
                loaded_content=loaded_content,
                placement_result=placement_result,
            )

        visual_profile_catalog = loaded_content.visual_profile_catalog
        router = build_v1_router(
            adjacency_finder=build_v1_junction_adjacency_finder(
                active_grid=active_grid,
                visual_profile_catalog=visual_profile_catalog,
            ),
            geometry_build_feasibility=build_v1_junction_geometry_build_feasibility(
                visual_profile_catalog=visual_profile_catalog,
            ),
            candidate_eligibility=build_v1_candidate_eligibility(),
        )
        route_orchestrator = build_v1_route_orchestrator(
            router=router,
            commit=V1RouteCommit(),
        )
        placement_orchestrator = build_v1_placement_orchestrator(
            runtime_snapshot_builder=build_v1_runtime_snapshot_builder(
                active_grid=active_grid,
                node_definitions=loaded_content.node_definitions,
            ),
            route_orchestrator=route_orchestrator,
        )
        placement_orchestration_result = placement_orchestrator(
            placement_snapshots=placement_result.seeds,
            schema_view=loaded_content.schema_view,
            route_requirements=loaded_content.route_requirements,
        )
        if placement_orchestration_result.status != "success":
            return CurrentGridSolveResult(
                status="routing_failure_on_current_grid",
                active_grid=active_grid,
                loaded_content=loaded_content,
                placement_result=placement_result,
                placement_orchestration_result=placement_orchestration_result,
            )

        return CurrentGridSolveResult(
            status="success",
            active_grid=active_grid,
            loaded_content=loaded_content,
            placement_result=placement_result,
            placement_orchestration_result=placement_orchestration_result,
            final_state=placement_orchestration_result.final_state,
        )


def build_v1_current_grid_solve_pipeline(
    max_placement_seeds: int = 1,
    minimum_same_row_gap: int = 1,
) -> V1CurrentGridSolvePipeline:
    """Bind the current concrete logical layers into one current-grid solve shell."""

    return V1CurrentGridSolvePipeline(
        max_placement_seeds=max_placement_seeds,
        minimum_same_row_gap=minimum_same_row_gap,
    )


def build_v1_current_grid_solve_pipeline_for_layout_profile(
    layout_profile: LayoutProfile,
    max_placement_seeds: int = 1,
) -> V1CurrentGridSolvePipeline:
    """Bind the current-grid solve shell from one explicit layout profile."""

    return build_v1_current_grid_solve_pipeline(
        max_placement_seeds=max_placement_seeds,
        minimum_same_row_gap=layout_profile.minimum_same_row_gap,
    )
