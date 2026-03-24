"""First minimal exact router for one fixed snapshot only.

This module runs exact-routing search inside one fixed placement/runtime
snapshot. It does not mutate committed runtime state, perform commit/update,
placement backtracking, or global route-preservation validation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from toolsv2.solver_common import (
    AdjacencyFinder,
    CandidateEligibility,
    EdgeTraversalMode,
    EntryContext,
    FrontierContext,
    GeometryBuildFeasibility,
    Junction,
    ObjectRef,
    PortEdgeId,
    PortRef,
    RouteRequirement,
    RouteRequirementSchemaView,
)
from toolsv2.entry_queries import directly_reachable_next_entry_contexts
from toolsv2.solver_runtime import Port, PortGraphState, RuntimeObjectSet, is_port_ref_usable


RouteStepKind = Literal["built_edge", "tentative_connection"]
RouterStatus = Literal["success", "failure_snapshot"]


def _object_ref_sort_key(object_ref: ObjectRef) -> tuple[str, str]:
    if isinstance(object_ref, Junction):
        return (
            "junction",
            f"{object_ref.x_rail_id}|{object_ref.y_rail_id}",
        )
    return ("node", str(object_ref))


def _port_ref_sort_key(port_ref: PortRef) -> tuple[tuple[str, str], str]:
    return (_object_ref_sort_key(port_ref.owner_ref), str(port_ref.owner_local_key))


def _entry_context_sort_key(
    entry_context: EntryContext,
) -> tuple[tuple[tuple[str, str], str], str]:
    return (
        _port_ref_sort_key(entry_context.current_port_ref),
        "" if entry_context.incoming_edge_id is None else str(entry_context.incoming_edge_id),
    )


def _ports_for_object_ref(
    runtime_objects: RuntimeObjectSet,
    object_ref: ObjectRef,
) -> tuple[Port, ...]:
    if isinstance(object_ref, Junction):
        for junction in runtime_objects.junctions:
            if junction.junction_id == object_ref:
                return junction.ports
        return ()

    for node in runtime_objects.nodes:
        if node.node_id == object_ref:
            return node.ports
    return ()


def _allowed_source_entry_contexts(
    runtime_objects: RuntimeObjectSet,
    schema_view: RouteRequirementSchemaView,
    route_requirement: RouteRequirement,
) -> tuple[EntryContext, ...]:
    source_port_keys = set(
        schema_view.source_port_keys(
            route_requirement.source_object_ref,
            route_requirement,
        )
    )
    return tuple(
        sorted(
            (
                EntryContext(current_port_ref=port.port_ref, incoming_edge_id=None)
                for port in _ports_for_object_ref(runtime_objects, route_requirement.source_object_ref)
                if port.port_ref.owner_local_key in source_port_keys
                and is_port_ref_usable(runtime_objects, port.port_ref)
            ),
            key=_entry_context_sort_key,
        )
    )


def _allowed_sink_port_refs(
    runtime_objects: RuntimeObjectSet,
    schema_view: RouteRequirementSchemaView,
    route_requirement: RouteRequirement,
) -> frozenset[PortRef]:
    sink_port_keys = set(
        schema_view.sink_port_keys(
            route_requirement.sink_object_ref,
            route_requirement,
        )
    )
    return frozenset(
        port.port_ref
        for port in _ports_for_object_ref(runtime_objects, route_requirement.sink_object_ref)
        if port.port_ref.owner_local_key in sink_port_keys
        and is_port_ref_usable(runtime_objects, port.port_ref)
    )


@dataclass(frozen=True, slots=True)
class TentativeRouteStep:
    """One tentative search step in a pure route trace."""

    step_kind: RouteStepKind
    from_entry_context: EntryContext
    to_entry_context: EntryContext
    via_edge_id: PortEdgeId | None = None
    new_edge_traversal_mode: EdgeTraversalMode | None = None

    def __post_init__(self) -> None:
        if self.step_kind == "built_edge":
            if self.via_edge_id is None:
                raise ValueError("built_edge steps require via_edge_id")
            if self.to_entry_context.incoming_edge_id != self.via_edge_id:
                raise ValueError(
                    "built_edge step to_entry_context.incoming_edge_id must match via_edge_id"
                )
            if self.new_edge_traversal_mode is not None:
                raise ValueError("built_edge steps must not declare new_edge_traversal_mode")
            return
        if self.via_edge_id is not None:
            raise ValueError("tentative_connection steps must not declare via_edge_id")
        if self.to_entry_context.incoming_edge_id is not None:
            raise ValueError(
                "tentative_connection steps must use an EntryContext with incoming_edge_id=None"
            )
        if self.new_edge_traversal_mode is None:
            object.__setattr__(self, "new_edge_traversal_mode", "bidirectional")


@dataclass(frozen=True, slots=True)
class TentativeRoutePlan:
    """A pure tentative route trace for one fixed snapshot."""

    route_requirement_id: str
    start_entry_context: EntryContext
    steps: tuple[TentativeRouteStep, ...]
    reached_sink_port_ref: PortRef


@dataclass(frozen=True, slots=True)
class RouterResult:
    """Router result scoped only to one fixed snapshot."""

    status: RouterStatus
    route_plan: TentativeRoutePlan | None = None

    def __post_init__(self) -> None:
        if self.status == "success":
            if self.route_plan is None:
                raise ValueError("success RouterResult requires route_plan")
            return
        if self.route_plan is not None:
            raise ValueError("failure_snapshot RouterResult must not include route_plan")


def _build_built_edge_steps(
    state: PortGraphState,
    current_entry_context: EntryContext,
) -> tuple[TentativeRouteStep, ...]:
    return tuple(
        TentativeRouteStep(
            step_kind="built_edge",
            from_entry_context=current_entry_context,
            to_entry_context=next_entry_context,
            via_edge_id=next_entry_context.incoming_edge_id,
        )
        for next_entry_context in sorted(
            directly_reachable_next_entry_contexts(state, current_entry_context),
            key=_entry_context_sort_key,
        )
    )


def _build_local_candidate_steps(
    runtime_objects: RuntimeObjectSet,
    schema_view: RouteRequirementSchemaView,
    route_requirement: RouteRequirement,
    adjacency_finder: AdjacencyFinder,
    geometry_build_feasibility: GeometryBuildFeasibility,
    candidate_eligibility: CandidateEligibility,
    current_entry_context: EntryContext,
) -> tuple[TentativeRouteStep, ...]:
    current_port_ref = current_entry_context.current_port_ref
    current_object_ref = current_port_ref.owner_ref
    frontier_context = FrontierContext(
        current_object_ref=current_object_ref,
        current_port_ref=current_port_ref,
    )
    relations = adjacency_finder(runtime_objects, frontier_context)
    steps: list[TentativeRouteStep] = []

    for relation in relations:
        candidate_port_refs = geometry_build_feasibility(
            runtime_objects,
            frontier_context,
            relation,
        )
        for candidate_port_ref in candidate_port_refs:
            if not candidate_eligibility(
                runtime_objects,
                schema_view,
                frontier_context,
                relation,
                route_requirement,
                candidate_port_ref,
            ):
                continue
            steps.append(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=current_entry_context,
                    to_entry_context=EntryContext(
                        current_port_ref=candidate_port_ref,
                        incoming_edge_id=None,
                    ),
                )
            )

    deduplicated: dict[EntryContext, TentativeRouteStep] = {}
    for step in sorted(
        steps,
        key=lambda step: _entry_context_sort_key(step.to_entry_context),
    ):
        deduplicated.setdefault(step.to_entry_context, step)
    return tuple(deduplicated.values())


def _reconstruct_route_plan(
    route_requirement: RouteRequirement,
    parent_steps: dict[EntryContext, TentativeRouteStep | None],
    terminal_entry_context: EntryContext,
) -> TentativeRoutePlan:
    steps: list[TentativeRouteStep] = []
    current_entry_context = terminal_entry_context

    while True:
        parent_step = parent_steps[current_entry_context]
        if parent_step is None:
            start_entry_context = current_entry_context
            break
        steps.append(parent_step)
        current_entry_context = parent_step.from_entry_context

    steps.reverse()
    return TentativeRoutePlan(
        route_requirement_id=route_requirement.requirement_id,
        start_entry_context=start_entry_context,
        steps=tuple(steps),
        reached_sink_port_ref=terminal_entry_context.current_port_ref,
    )


@dataclass(frozen=True, slots=True)
class V1Router:
    """Minimal exact router for one fixed snapshot only."""

    adjacency_finder: AdjacencyFinder
    geometry_build_feasibility: GeometryBuildFeasibility
    candidate_eligibility: CandidateEligibility

    def __call__(
        self,
        state: PortGraphState,
        schema_view: RouteRequirementSchemaView,
        route_requirement: RouteRequirement,
    ) -> RouterResult:
        if not isinstance(state, PortGraphState):
            raise TypeError("state must be PortGraphState")
        if not isinstance(route_requirement, RouteRequirement):
            raise TypeError("route_requirement must be RouteRequirement")

        runtime_objects = state.objects
        start_entry_contexts = _allowed_source_entry_contexts(
            runtime_objects,
            schema_view,
            route_requirement,
        )
        sink_port_refs = _allowed_sink_port_refs(
            runtime_objects,
            schema_view,
            route_requirement,
        )

        if not start_entry_contexts or not sink_port_refs:
            return RouterResult(status="failure_snapshot")

        queue: deque[EntryContext] = deque(start_entry_contexts)
        parent_steps: dict[EntryContext, TentativeRouteStep | None] = {
            entry_context: None
            for entry_context in start_entry_contexts
        }

        for start_entry_context in start_entry_contexts:
            if start_entry_context.current_port_ref in sink_port_refs:
                return RouterResult(
                    status="success",
                    route_plan=TentativeRoutePlan(
                        route_requirement_id=route_requirement.requirement_id,
                        start_entry_context=start_entry_context,
                        steps=(),
                        reached_sink_port_ref=start_entry_context.current_port_ref,
                    ),
                )

        while queue:
            current_entry_context = queue.popleft()
            next_steps = (
                _build_built_edge_steps(state, current_entry_context)
                + _build_local_candidate_steps(
                    runtime_objects,
                    schema_view,
                    route_requirement,
                    self.adjacency_finder,
                    self.geometry_build_feasibility,
                    self.candidate_eligibility,
                    current_entry_context,
                )
            )

            for next_step in next_steps:
                next_entry_context = next_step.to_entry_context
                if next_entry_context in parent_steps:
                    continue
                parent_steps[next_entry_context] = next_step
                if next_entry_context.current_port_ref in sink_port_refs:
                    return RouterResult(
                        status="success",
                        route_plan=_reconstruct_route_plan(
                            route_requirement,
                            parent_steps,
                            next_entry_context,
                        ),
                    )
                queue.append(next_entry_context)

        return RouterResult(status="failure_snapshot")


def build_v1_router(
    adjacency_finder: AdjacencyFinder,
    geometry_build_feasibility: GeometryBuildFeasibility,
    candidate_eligibility: CandidateEligibility,
) -> V1Router:
    """Bind the current lower-layer routing callables into a minimal v1 router."""

    return V1Router(
        adjacency_finder=adjacency_finder,
        geometry_build_feasibility=geometry_build_feasibility,
        candidate_eligibility=candidate_eligibility,
    )
