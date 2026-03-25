"""First concrete source-grouped routing orchestration for one fixed snapshot.

This module sequences the existing pure router and local commit layers across
explicit source-owned requirement groups. It maintains per-source directed flow
semantics over the physically built graph, allowing additive fanout and reuse
of already built suffixes while rejecting source-flow shapes that create
cycles or reach unintended non-junction endpoints. It does not retry alternate
routes, backtrack already committed requirements, mutate placement, or perform
refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from toolsv2.route_commit import CommitResult
from toolsv2.router import RouterResult, TentativeRoutePlan
from toolsv2.solver_common import (
    Junction,
    ObjectRef,
    PortId,
    PortRef,
    RouteRequirement,
    RouteRequirementSchemaView,
)
from toolsv2.solver_runtime import Port, PortEdge, PortGraphState, RuntimeObjectSet, is_port_ref_usable


OrchestrationStatus = Literal["success", "failure_snapshot"]
FailureStage = Literal["router", "commit"]

RoutePlanner = Callable[
    [PortGraphState, RouteRequirementSchemaView, RouteRequirement],
    RouterResult,
]
RouteCommitter = Callable[[PortGraphState, TentativeRoutePlan], CommitResult]
SourceFlowValidator = Callable[
    [
        PortGraphState,
        RouteRequirementSchemaView,
        tuple[RouteRequirement, ...],
        RouteRequirement,
        TentativeRoutePlan,
        frozenset[tuple[PortRef, PortRef]],
    ],
    bool,
]


def _object_ref_sort_key(object_ref: ObjectRef) -> tuple[str, str]:
    if isinstance(object_ref, Junction):
        return ("junction", f"{object_ref.x_rail_id}|{object_ref.y_rail_id}")
    return ("node", str(object_ref))


def _port_ref_sort_key(port_ref: PortRef) -> tuple[tuple[str, str], str]:
    return (_object_ref_sort_key(port_ref.owner_ref), str(port_ref.owner_local_key))


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


def _source_port_keys_for_source(
    schema_view: RouteRequirementSchemaView,
    source_object_ref: ObjectRef,
    route_requirements: tuple[RouteRequirement, ...],
) -> tuple[PortId, ...]:
    ordered_keys: list[PortId] = []
    seen_keys: set[PortId] = set()
    for route_requirement in route_requirements:
        if route_requirement.source_object_ref != source_object_ref:
            continue
        for port_key in schema_view.source_port_keys(source_object_ref, route_requirement):
            if port_key in seen_keys:
                continue
            seen_keys.add(port_key)
            ordered_keys.append(port_key)
    return tuple(ordered_keys)


def _sink_port_refs_for_source(
    runtime_objects: RuntimeObjectSet,
    schema_view: RouteRequirementSchemaView,
    source_object_ref: ObjectRef,
    route_requirements: tuple[RouteRequirement, ...],
) -> frozenset[PortRef]:
    sink_port_refs: set[PortRef] = set()
    for route_requirement in route_requirements:
        if route_requirement.source_object_ref != source_object_ref:
            continue
        sink_port_keys = set(
            schema_view.sink_port_keys(
                route_requirement.sink_object_ref,
                route_requirement,
            )
        )
        for port in _ports_for_object_ref(runtime_objects, route_requirement.sink_object_ref):
            if (
                port.port_ref.owner_local_key in sink_port_keys
                and is_port_ref_usable(runtime_objects, port.port_ref)
            ):
                sink_port_refs.add(port.port_ref)
    return frozenset(sink_port_refs)


def _source_start_entry_contexts(
    runtime_objects: RuntimeObjectSet,
    schema_view: RouteRequirementSchemaView,
    source_object_ref: ObjectRef,
    route_requirements: tuple[RouteRequirement, ...],
) -> tuple[PortRef, ...]:
    source_port_keys = set(
        _source_port_keys_for_source(schema_view, source_object_ref, route_requirements)
    )
    if not source_port_keys:
        return ()
    return tuple(
        sorted(
            (
                port.port_ref
                for port in _ports_for_object_ref(runtime_objects, source_object_ref)
                if port.port_ref.owner_local_key in source_port_keys
                and is_port_ref_usable(runtime_objects, port.port_ref)
            ),
            key=_port_ref_sort_key,
        )
    )


def _group_route_requirements_by_source(
    route_requirements: tuple[RouteRequirement, ...],
) -> tuple[tuple[ObjectRef, tuple[RouteRequirement, ...]], ...]:
    ordered_sources: list[ObjectRef] = []
    grouped: dict[ObjectRef, list[RouteRequirement]] = {}

    for route_requirement in route_requirements:
        if route_requirement.source_object_ref not in grouped:
            grouped[route_requirement.source_object_ref] = []
            ordered_sources.append(route_requirement.source_object_ref)
        grouped[route_requirement.source_object_ref].append(route_requirement)

    return tuple(
        (
            source_object_ref,
            tuple(grouped[source_object_ref]),
        )
        for source_object_ref in ordered_sources
    )


def _flow_arcs_from_route_plan(
    route_plan: TentativeRoutePlan,
) -> tuple[tuple[PortRef, PortRef], ...]:
    return tuple(
        (
            step.from_entry_context.current_port_ref,
            step.to_entry_context.current_port_ref,
        )
        for step in route_plan.steps
    )


def _reachable_port_refs_from_roots(
    root_port_refs: tuple[PortRef, ...],
    flow_arcs: frozenset[tuple[PortRef, PortRef]],
) -> frozenset[PortRef]:
    adjacency: dict[PortRef, list[PortRef]] = {}
    for from_port_ref, to_port_ref in flow_arcs:
        adjacency.setdefault(from_port_ref, []).append(to_port_ref)

    seen = set(root_port_refs)
    queue = list(root_port_refs)
    while queue:
        current_port_ref = queue.pop(0)
        for next_port_ref in adjacency.get(current_port_ref, ()):
            if next_port_ref in seen:
                continue
            seen.add(next_port_ref)
            queue.append(next_port_ref)
    return frozenset(seen)


def _reachable_flow_is_acyclic(
    root_port_refs: tuple[PortRef, ...],
    flow_arcs: frozenset[tuple[PortRef, PortRef]],
    reachable_port_refs: frozenset[PortRef],
) -> bool:
    adjacency: dict[PortRef, list[PortRef]] = {}
    indegree_by_port_ref: dict[PortRef, int] = {
        port_ref: 0
        for port_ref in reachable_port_refs
    }
    for from_port_ref, to_port_ref in flow_arcs:
        if from_port_ref not in reachable_port_refs or to_port_ref not in reachable_port_refs:
            continue
        adjacency.setdefault(from_port_ref, []).append(to_port_ref)
        indegree_by_port_ref[to_port_ref] = indegree_by_port_ref.get(to_port_ref, 0) + 1

    for root_port_ref in root_port_refs:
        if indegree_by_port_ref.get(root_port_ref, 0) != 0:
            return False

    queue = [
        port_ref
        for port_ref, indegree in sorted(
            indegree_by_port_ref.items(),
            key=lambda item: _port_ref_sort_key(item[0]),
        )
        if indegree == 0
    ]
    visited_count = 0
    while queue:
        current_port_ref = queue.pop(0)
        visited_count += 1
        for next_port_ref in adjacency.get(current_port_ref, ()):
            indegree_by_port_ref[next_port_ref] -= 1
            if indegree_by_port_ref[next_port_ref] == 0:
                queue.append(next_port_ref)

    return visited_count == len(reachable_port_refs)


def _is_source_flow_extension_valid(
    current_state: PortGraphState,
    schema_view: RouteRequirementSchemaView,
    route_requirements: tuple[RouteRequirement, ...],
    route_requirement: RouteRequirement,
    route_plan: TentativeRoutePlan,
    existing_source_flow_arcs: frozenset[tuple[PortRef, PortRef]],
) -> bool:
    current_source_object_ref = route_requirement.source_object_ref
    root_port_refs = _source_start_entry_contexts(
        current_state.objects,
        schema_view,
        current_source_object_ref,
        route_requirements,
    )
    if not root_port_refs:
        return False
    if route_plan.start_entry_context.current_port_ref not in root_port_refs:
        return False

    route_flow_arcs = _flow_arcs_from_route_plan(route_plan)
    updated_source_flow_arcs = frozenset(existing_source_flow_arcs.union(route_flow_arcs))
    reachable_port_refs = _reachable_port_refs_from_roots(
        root_port_refs,
        updated_source_flow_arcs,
    )
    for from_port_ref, to_port_ref in updated_source_flow_arcs:
        if from_port_ref not in reachable_port_refs or to_port_ref not in reachable_port_refs:
            return False
    if not _reachable_flow_is_acyclic(
        root_port_refs,
        updated_source_flow_arcs,
        reachable_port_refs,
    ):
        return False

    allowed_sink_port_refs = _sink_port_refs_for_source(
        current_state.objects,
        schema_view,
        current_source_object_ref,
        route_requirements,
    )
    root_port_ref_set = set(root_port_refs)
    for port_ref in reachable_port_refs:
        owner_ref = port_ref.owner_ref
        if owner_ref == current_source_object_ref:
            if port_ref not in root_port_ref_set:
                return False
            continue
        if isinstance(owner_ref, Junction):
            continue
        if port_ref not in allowed_sink_port_refs:
            return False

    return True


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
    """Thin source-grouped router+commit orchestration for one fixed snapshot."""

    router: RoutePlanner
    commit: RouteCommitter
    source_flow_validator: SourceFlowValidator = _is_source_flow_extension_valid

    def __call__(
        self,
        initial_state: PortGraphState,
        schema_view: RouteRequirementSchemaView,
        route_requirements: tuple[RouteRequirement, ...],
    ) -> OrchestrationResult:
        if not isinstance(initial_state, PortGraphState):
            raise TypeError("initial_state must be PortGraphState")
        for route_requirement in route_requirements:
            if not isinstance(route_requirement, RouteRequirement):
                raise TypeError("route_requirements must contain RouteRequirement values")

        requirement_indices = {
            route_requirement.requirement_id: requirement_index
            for requirement_index, route_requirement in enumerate(route_requirements)
        }
        current_state = initial_state
        source_flow_arcs_by_source: dict[ObjectRef, frozenset[tuple[PortRef, PortRef]]] = {}
        completed: list[CommittedRequirementRecord] = []

        for _, grouped_requirements in _group_route_requirements_by_source(route_requirements):
            for route_requirement in grouped_requirements:
                requirement_index = requirement_indices[route_requirement.requirement_id]

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

                current_source_flow_arcs = source_flow_arcs_by_source.get(
                    route_requirement.source_object_ref,
                    frozenset(),
                )
                if not self.source_flow_validator(
                    current_state,
                    schema_view,
                    route_requirements,
                    route_requirement,
                    router_result.route_plan,
                    current_source_flow_arcs,
                ):
                    return OrchestrationResult(
                        status="failure_snapshot",
                        completed=tuple(completed),
                        failed_requirement_index=requirement_index,
                        failed_requirement_id=route_requirement.requirement_id,
                        failure_stage="commit",
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
                source_flow_arcs_by_source[route_requirement.source_object_ref] = frozenset(
                    current_source_flow_arcs.union(
                        _flow_arcs_from_route_plan(router_result.route_plan)
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
