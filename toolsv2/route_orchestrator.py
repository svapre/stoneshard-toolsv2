"""First concrete multi-requirement orchestration for one fixed snapshot.

This module sequences the existing pure router and pure commit layers across an
explicit requirement order. It does not reorder requirements, retry alternate
routes, backtrack already committed requirements, mutate placement, or perform
refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from toolsv2.route_commit import CommitResult
from toolsv2.router import RouterResult, TentativeRoutePlan
from toolsv2.solver_common import RouteRequirement, RouteRequirementSchemaView
from toolsv2.solver_runtime import PortEdge, PortGraphState


OrchestrationStatus = Literal["success", "failure_snapshot"]
FailureStage = Literal["router", "commit"]

RoutePlanner = Callable[
    [PortGraphState, RouteRequirementSchemaView, RouteRequirement],
    RouterResult,
]
RouteCommitter = Callable[[PortGraphState, TentativeRoutePlan], CommitResult]


@dataclass(frozen=True, slots=True)
class CommittedRequirementRecord:
    """One successfully routed and committed requirement in input order."""

    route_requirement_id: str
    route_plan: TentativeRoutePlan
    added_edges: tuple[PortEdge, ...]


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Result of routing and committing multiple requirements on one snapshot."""

    status: OrchestrationStatus
    completed: tuple[CommittedRequirementRecord, ...] = ()
    final_state: PortGraphState | None = None
    failed_requirement_index: int | None = None
    failed_requirement_id: str | None = None
    failure_stage: FailureStage | None = None
    last_successful_state: PortGraphState | None = None

    def __post_init__(self) -> None:
        if self.status == "success":
            if self.final_state is None:
                raise ValueError("success OrchestrationResult requires final_state")
            if self.failed_requirement_index is not None:
                raise ValueError("success OrchestrationResult must not include failed_requirement_index")
            if self.failed_requirement_id is not None:
                raise ValueError("success OrchestrationResult must not include failed_requirement_id")
            if self.failure_stage is not None:
                raise ValueError("success OrchestrationResult must not include failure_stage")
            if self.last_successful_state is not None:
                raise ValueError("success OrchestrationResult must not include last_successful_state")
            return

        if self.final_state is not None:
            raise ValueError("failure_snapshot OrchestrationResult must not include final_state")
        if self.failed_requirement_index is None:
            raise ValueError("failure_snapshot OrchestrationResult requires failed_requirement_index")
        if self.failed_requirement_id is None:
            raise ValueError("failure_snapshot OrchestrationResult requires failed_requirement_id")
        if self.failure_stage is None:
            raise ValueError("failure_snapshot OrchestrationResult requires failure_stage")
        if self.last_successful_state is None:
            raise ValueError("failure_snapshot OrchestrationResult requires last_successful_state")


@dataclass(frozen=True, slots=True)
class V1RouteOrchestrator:
    """Thin sequential router+commit orchestration for one fixed snapshot."""

    router: RoutePlanner
    commit: RouteCommitter

    def __call__(
        self,
        initial_state: PortGraphState,
        schema_view: RouteRequirementSchemaView,
        route_requirements: tuple[RouteRequirement, ...],
    ) -> OrchestrationResult:
        if not isinstance(initial_state, PortGraphState):
            raise TypeError("initial_state must be PortGraphState")

        current_state = initial_state
        completed: list[CommittedRequirementRecord] = []

        for requirement_index, route_requirement in enumerate(route_requirements):
            if not isinstance(route_requirement, RouteRequirement):
                raise TypeError("route_requirements must contain RouteRequirement values")

            router_result = self.router(current_state, schema_view, route_requirement)
            if router_result.status != "success" or router_result.route_plan is None:
                return OrchestrationResult(
                    status="failure_snapshot",
                    completed=tuple(completed),
                    failed_requirement_index=requirement_index,
                    failed_requirement_id=route_requirement.requirement_id,
                    failure_stage="router",
                    last_successful_state=current_state,
                )

            commit_result = self.commit(current_state, router_result.route_plan)
            if commit_result.status != "success" or commit_result.new_state is None:
                return OrchestrationResult(
                    status="failure_snapshot",
                    completed=tuple(completed),
                    failed_requirement_index=requirement_index,
                    failed_requirement_id=route_requirement.requirement_id,
                    failure_stage="commit",
                    last_successful_state=current_state,
                )

            completed.append(
                CommittedRequirementRecord(
                    route_requirement_id=route_requirement.requirement_id,
                    route_plan=router_result.route_plan,
                    added_edges=commit_result.added_edges,
                )
            )
            current_state = commit_result.new_state

        return OrchestrationResult(
            status="success",
            completed=tuple(completed),
            final_state=current_state,
        )


def build_v1_route_orchestrator(
    router: RoutePlanner,
    commit: RouteCommitter,
) -> V1RouteOrchestrator:
    """Bind the current router and commit callables into the v1 orchestrator."""

    return V1RouteOrchestrator(
        router=router,
        commit=commit,
    )
