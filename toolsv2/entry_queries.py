"""Pure entry-context graph queries over built runtime edges.

This module operates on current source-of-truth runtime state plus the graph
index view. It does not perform router search, pathfinding policy,
commit/update behavior, or global route-correctness validation.
"""

from __future__ import annotations

from toolsv2.solver_common import EntryContext, PortRef
from toolsv2.solver_runtime import (
    PortEdge,
    PortGraphState,
    is_edge_id_usable,
    is_port_ref_usable,
)


def _edge_lookup(state: PortGraphState) -> dict[str, PortEdge]:
    return {
        str(edge.edge_id): edge
        for edge in state.objects.edges
    }


def is_entry_context_usable(
    state: PortGraphState,
    entry_context: EntryContext,
) -> bool:
    """Return whether one entry context is currently usable in source-of-truth state."""

    if not isinstance(state, PortGraphState):
        raise TypeError("state must be PortGraphState")
    if not isinstance(entry_context, EntryContext):
        raise TypeError("entry_context must be EntryContext")

    try:
        if not is_port_ref_usable(state.objects, entry_context.current_port_ref):
            return False
    except KeyError:
        return False

    if entry_context.incoming_edge_id is None:
        return True

    if entry_context.incoming_edge_id not in state.graph.edge_ids:
        return False

    try:
        if not is_edge_id_usable(state.objects, entry_context.incoming_edge_id):
            return False
    except KeyError:
        return False

    edge = _edge_lookup(state).get(str(entry_context.incoming_edge_id))
    if edge is None:
        return False
    return entry_context.current_port_ref in (edge.port_ref_a, edge.port_ref_b)


def _other_port_ref(edge: PortEdge, current_port_ref: PortRef) -> PortRef | None:
    if current_port_ref == edge.port_ref_a:
        if edge.traversal_mode in ("bidirectional", "a_to_b"):
            return edge.port_ref_b
        return None
    if current_port_ref == edge.port_ref_b:
        if edge.traversal_mode in ("bidirectional", "b_to_a"):
            return edge.port_ref_a
        return None
    return None


def directly_reachable_next_entry_contexts(
    state: PortGraphState,
    entry_context: EntryContext,
) -> tuple[EntryContext, ...]:
    """Return one-step next entry contexts reachable through current built edges."""

    if not is_entry_context_usable(state, entry_context):
        return ()

    current_port_ref = entry_context.current_port_ref
    edge_lookup = _edge_lookup(state)
    next_contexts: list[EntryContext] = []

    for edge_id in state.graph.edge_ids:
        edge = edge_lookup.get(str(edge_id))
        if edge is None:
            continue
        if not is_edge_id_usable(state.objects, edge.edge_id):
            continue
        target_port_ref = _other_port_ref(edge, current_port_ref)
        if target_port_ref is None:
            continue
        next_contexts.append(
            EntryContext(
                current_port_ref=target_port_ref,
                incoming_edge_id=edge.edge_id,
            )
        )

    return tuple(next_contexts)
