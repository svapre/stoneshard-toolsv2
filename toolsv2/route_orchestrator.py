"""First concrete source-grouped routing orchestration for one fixed snapshot.

This module sequences the existing pure router and local commit layers across
explicit source-owned requirement groups. It allows additive fanout inside the
currently committed source tree while rejecting cross-source leakage. It does
not retry alternate routes, backtrack already committed requirements, mutate
placement, or perform refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from toolsv2.entry_queries import directly_reachable_next_entry_contexts, is_entry_context_usable
from toolsv2.route_commit import CommitResult
from toolsv2.router import RouterResult, TentativeRoutePlan
from toolsv2.solver_common import (
    EntryContext,
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
SourceReachabilityValidator = Callable[
    [
        PortGraphState,
        PortGraphState,
        RouteRequirementSchemaView,
        tuple[RouteRequirement, ...],
        ObjectRef,
    ],
    bool,
]


def _object_ref_sort_key(object_ref: ObjectRef) -> tuple[str, str]:
    if isinstance(object_ref, Junction):
        return ("junction", f"{object_ref.x_rail_id}|{object_ref.y_rail_id}")
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
) -> tuple[EntryContext, ...]:
    source_port_keys = set(
        _source_port_keys_for_source(schema_view, source_object_ref, route_requirements)
    )
    if not source_port_keys:
        return ()
    return tuple(
        sorted(
            (
                EntryContext(current_port_ref=port.port_ref, incoming_edge_id=None)
                for port in _ports_for_object_ref(runtime_objects, source_object_ref)
                if port.port_ref.owner_local_key in source_port_keys
                and is_port_ref_usable(runtime_objects, port.port_ref)
            ),
            key=_entry_context_sort_key,
        )
    )


def _reachable_entry_contexts_from_sources(
    state: PortGraphState,
    start_entry_contexts: tuple[EntryContext, ...],
) -> frozenset[EntryContext]:
    queue = [
        entry_context
        for entry_context in start_entry_contexts
        if is_entry_context_usable(state, entry_context)
    ]
    seen = set(queue)

    while queue:
        current_entry_context = queue.pop(0)
        for next_entry_context in directly_reachable_next_entry_contexts(state, current_entry_context):
            if next_entry_context in seen:
                continue
            seen.add(next_entry_context)
            queue.append(next_entry_context)

    return frozenset(seen)


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


def _validate_source_group_reachability(
    pre_commit_state: PortGraphState,
    post_commit_state: PortGraphState,
    schema_view: RouteRequirementSchemaView,
    route_requirements: tuple[RouteRequirement, ...],
    current_source_object_ref: ObjectRef,
) -> bool:
    source_refs = tuple(
        dict.fromkeys(
            route_requirement.source_object_ref
            for route_requirement in route_requirements
        )
    )

    for source_object_ref in source_refs:
        pre_start_entry_contexts = _source_start_entry_contexts(
            pre_commit_state.objects,
            schema_view,
            source_object_ref,
            route_requirements,
        )
        post_start_entry_contexts = _source_start_entry_contexts(
            post_commit_state.objects,
            schema_view,
            source_object_ref,
            route_requirements,
        )
        pre_reachable = _reachable_entry_contexts_from_sources(
            pre_commit_state,
            pre_start_entry_contexts,
        )
        post_reachable = _reachable_entry_contexts_from_sources(
            post_commit_state,
            post_start_entry_contexts,
        )
        if source_object_ref != current_source_object_ref and pre_reachable != post_reachable:
            return False

    allowed_sink_port_refs = _sink_port_refs_for_source(
        post_commit_state.objects,
        schema_view,
        current_source_object_ref,
        route_requirements,
    )
    current_source_reachable = _reachable_entry_contexts_from_sources(
        post_commit_state,
        _source_start_entry_contexts(
            post_commit_state.objects,
            schema_view,
            current_source_object_ref,
            route_requirements,
        ),
    )
    for entry_context in current_source_reachable:
        owner_ref = entry_context.current_port_ref.owner_ref
        if owner_ref == current_source_object_ref or isinstance(owner_ref, Junction):
            continue
        if entry_context.current_port_ref not in allowed_sink_port_refs:
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
    source_reachability_validator: SourceReachabilityValidator = _validate_source_group_reachability

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
                if not self.source_reachability_validator(
                    current_state,
                    commit_result.new_state,
                    schema_view,
                    route_requirements,
                    route_requirement.source_object_ref,
                ):
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
