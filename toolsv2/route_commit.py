"""First concrete validate-and-apply route commit for one fixed snapshot.

This module validates a tentative route plan against the current snapshot,
materializes new built edges, and returns a new snapshot without mutating the
original. It owns only local validate-and-apply behavior for one tentative
plan. Source-owned route-tree preservation/cross-source leakage checks live in
the orchestration layer above it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from toolsv2.entry_queries import directly_reachable_next_entry_contexts, is_entry_context_usable
from toolsv2.router import TentativeRoutePlan, TentativeRouteStep
from toolsv2.solver_common import EdgeTraversalMode, EntryContext, Junction, ObjectRef, PortEdgeId, PortRef
from toolsv2.solver_runtime import (
    PortEdge,
    PortGraphIndex,
    PortGraphState,
    RuntimeObjectSet,
    can_port_ref_accept_new_attachment,
    is_edge_id_usable,
    is_port_ref_usable,
)


CommitStatus = Literal["success", "failure_snapshot"]


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


def _edge_lookup(state: PortGraphState) -> dict[PortEdgeId, PortEdge]:
    return {
        edge.edge_id: edge
        for edge in state.objects.edges
    }


def _port_pair_key(port_ref_a: PortRef, port_ref_b: PortRef) -> tuple[PortRef, PortRef]:
    ordered = tuple(sorted((port_ref_a, port_ref_b), key=_port_ref_sort_key))
    return ordered[0], ordered[1]


def _make_edge_id(route_plan: TentativeRoutePlan, step_index: int) -> PortEdgeId:
    return PortEdgeId(f"committed::{route_plan.route_requirement_id}::step::{step_index}")


def _derived_scope_and_owner(
    port_ref_a: PortRef,
    port_ref_b: PortRef,
) -> tuple[str, ObjectRef | None]:
    if port_ref_a.owner_ref == port_ref_b.owner_ref:
        return "internal", port_ref_a.owner_ref
    return "external", None


def _materialize_added_edges(
    current_state: PortGraphState,
    route_plan: TentativeRoutePlan,
) -> tuple[tuple[PortEdge, ...], dict[int, PortEdgeId]] | None:
    current_edge_lookup = _edge_lookup(current_state)
    existing_edge_ids = set(current_edge_lookup)
    existing_pairs = {
        _port_pair_key(edge.port_ref_a, edge.port_ref_b)
        for edge in current_state.objects.edges
    }
    attachment_counts: dict[PortRef, int] = {}
    for edge in current_state.objects.edges:
        if not edge.is_active:
            continue
        attachment_counts[edge.port_ref_a] = attachment_counts.get(edge.port_ref_a, 0) + 1
        attachment_counts[edge.port_ref_b] = attachment_counts.get(edge.port_ref_b, 0) + 1
    base_attachment_counts = dict(attachment_counts)
    added_edges: list[PortEdge] = []
    created_edge_ids_by_step_index: dict[int, PortEdgeId] = {}

    for step_index, step in enumerate(route_plan.steps):
        if step.step_kind != "tentative_connection":
            continue

        from_port_ref = step.from_entry_context.current_port_ref
        to_port_ref = step.to_entry_context.current_port_ref
        if from_port_ref == to_port_ref:
            return None
        try:
            if not is_port_ref_usable(current_state.objects, from_port_ref):
                return None
            if not is_port_ref_usable(current_state.objects, to_port_ref):
                return None
            if not can_port_ref_accept_new_attachment(
                current_state.objects,
                from_port_ref,
                additional_attachments=(
                    attachment_counts.get(from_port_ref, 0)
                    - base_attachment_counts.get(from_port_ref, 0)
                    + 1
                ),
            ):
                return None
            if not can_port_ref_accept_new_attachment(
                current_state.objects,
                to_port_ref,
                additional_attachments=(
                    attachment_counts.get(to_port_ref, 0)
                    - base_attachment_counts.get(to_port_ref, 0)
                    + 1
                ),
            ):
                return None
        except KeyError:
            return None

        pair_key = _port_pair_key(from_port_ref, to_port_ref)
        if pair_key in existing_pairs:
            return None

        edge_id = _make_edge_id(route_plan, step_index)
        if edge_id in existing_edge_ids:
            return None
        existing_edge_ids.add(edge_id)
        existing_pairs.add(pair_key)
        created_edge_ids_by_step_index[step_index] = edge_id
        attachment_counts[from_port_ref] = attachment_counts.get(from_port_ref, 0) + 1
        attachment_counts[to_port_ref] = attachment_counts.get(to_port_ref, 0) + 1

        scope, owner_object_ref = _derived_scope_and_owner(from_port_ref, to_port_ref)
        added_edges.append(
            PortEdge(
                edge_id=edge_id,
                port_ref_a=from_port_ref,
                port_ref_b=to_port_ref,
                scope=scope,  # type: ignore[arg-type]
                traversal_mode=step.new_edge_traversal_mode or "bidirectional",
                owner_object_ref=owner_object_ref,
            )
        )

    return tuple(added_edges), created_edge_ids_by_step_index


def _build_post_commit_state(
    current_state: PortGraphState,
    added_edges: tuple[PortEdge, ...],
) -> PortGraphState:
    added_port_refs = tuple(
        dict.fromkeys(
            port_ref
            for edge in added_edges
            for port_ref in (edge.port_ref_a, edge.port_ref_b)
        )
    )
    return PortGraphState(
        objects=RuntimeObjectSet(
            nodes=current_state.objects.nodes,
            junctions=current_state.objects.junctions,
            edges=current_state.objects.edges + added_edges,
        ),
        graph=PortGraphIndex(
            port_refs=tuple(dict.fromkeys(current_state.graph.port_refs + added_port_refs)),
            edge_ids=current_state.graph.edge_ids + tuple(edge.edge_id for edge in added_edges),
            attributes=current_state.graph.attributes,
        ),
    )


def _replay_route_plan_in_state(
    state: PortGraphState,
    route_plan: TentativeRoutePlan,
    created_edge_ids_by_step_index: dict[int, PortEdgeId],
) -> bool:
    actual_current_entry_context = route_plan.start_entry_context
    if not is_entry_context_usable(state, actual_current_entry_context):
        return False

    for step_index, step in enumerate(route_plan.steps):
        if step.from_entry_context.current_port_ref != actual_current_entry_context.current_port_ref:
            return False

        next_entry_contexts = directly_reachable_next_entry_contexts(state, actual_current_entry_context)
        if step.step_kind == "built_edge":
            expected_edge_id = step.via_edge_id
        else:
            expected_edge_id = created_edge_ids_by_step_index.get(step_index)
            if expected_edge_id is None:
                return False

        matching_context = next(
            (
                next_entry_context
                for next_entry_context in next_entry_contexts
                if next_entry_context.current_port_ref == step.to_entry_context.current_port_ref
                and next_entry_context.incoming_edge_id == expected_edge_id
            ),
            None,
        )
        if matching_context is None:
            return False
        actual_current_entry_context = matching_context

    return actual_current_entry_context.current_port_ref == route_plan.reached_sink_port_ref


@dataclass(frozen=True, slots=True)
class CommitResult:
    """Commit result scoped only to one fixed snapshot and one tentative plan."""

    status: CommitStatus
    new_state: PortGraphState | None = None
    added_edges: tuple[PortEdge, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "success":
            if self.new_state is None:
                raise ValueError("success CommitResult requires new_state")
            return
        if self.new_state is not None:
            raise ValueError("failure_snapshot CommitResult must not include new_state")
        if self.added_edges:
            raise ValueError("failure_snapshot CommitResult must not include added_edges")


@dataclass(frozen=True, slots=True)
class V1RouteCommit:
    """First concrete validate-and-apply commit layer for one fixed snapshot."""

    def __call__(
        self,
        current_state: PortGraphState,
        route_plan: TentativeRoutePlan,
    ) -> CommitResult:
        if not isinstance(current_state, PortGraphState):
            raise TypeError("current_state must be PortGraphState")
        if not isinstance(route_plan, TentativeRoutePlan):
            raise TypeError("route_plan must be TentativeRoutePlan")

        materialization = _materialize_added_edges(current_state, route_plan)
        if materialization is None:
            return CommitResult(status="failure_snapshot")
        added_edges, created_edge_ids_by_step_index = materialization

        post_commit_state = _build_post_commit_state(current_state, added_edges)

        if not _replay_route_plan_in_state(post_commit_state, route_plan, created_edge_ids_by_step_index):
            return CommitResult(status="failure_snapshot")

        return CommitResult(
            status="success",
            new_state=post_commit_state,
            added_edges=added_edges,
        )


def build_v1_route_commit() -> V1RouteCommit:
    """Return the concrete v1 commit layer."""

    return V1RouteCommit()
