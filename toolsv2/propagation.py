"""Fixed-point propagation for the frozen structural subset only.

This module operates on already-built ``NodeDomain`` junction sets. It
implements only the safe propagation subset that can be expressed without
routing or screening:

- tier propagation
- row-order propagation
- same-row spacing propagation
- occupancy propagation
- singleton collapse
- empty-domain contradiction detection

This module does not implement:

- screening
- reachability
- port-based pre-routing support filtering
- exact routing
- lock rules
- symmetry-based pruning

Important limitation:

- Row propagation is limited to the same small 3-node and 4-node ordered-row
  cases already supported by ``domain_builder.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from toolsv2.domain_builder import (
    NodePlacementMetadata,
    OrderedSameRowGroup,
    build_authored_tier_dom_y,
    build_dynamic_dom_y,
)
from toolsv2.solver_types import ActiveGridState, Junction, LogicalXRailId, NodeDomain, NodeId


_SAFE_ORDERED_ROW_RAIL_COUNT = 7
_SAFE_ORDERED_ROW_NODE_COUNTS = frozenset({3, 4})
_SAFE_ONE_GAP = 1


@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Result of fixed-point structural propagation."""

    domains: dict[NodeId, NodeDomain]
    has_contradiction: bool
    contradiction_node_ids: tuple[NodeId, ...] = ()


def _ordered_active_x_rail_ids(active_grid: ActiveGridState) -> tuple[LogicalXRailId, ...]:
    return tuple(
        rail.rail_id
        for rail in sorted(active_grid.x_rails, key=lambda rail: rail.order)
    )


def _active_x_lookup(active_grid: ActiveGridState) -> set[str]:
    return {str(rail.rail_id) for rail in active_grid.x_rails}


def _active_y_lookup(active_grid: ActiveGridState) -> set[str]:
    return {str(rail.rail_id) for rail in active_grid.y_rails}


def _node_metadata_lookup(
    node_metadata: Sequence[NodePlacementMetadata],
) -> dict[NodeId, NodePlacementMetadata]:
    metadata_by_node_id = {metadata.node_id: metadata for metadata in node_metadata}
    if len(metadata_by_node_id) != len(tuple(node_metadata)):
        raise ValueError("node_metadata contains duplicate node ids")
    return metadata_by_node_id


def _validate_domains_on_active_grid(
    active_grid: ActiveGridState,
    domains: dict[NodeId, NodeDomain],
) -> None:
    active_x_ids = _active_x_lookup(active_grid)
    active_y_ids = _active_y_lookup(active_grid)

    for node_id, domain in domains.items():
        for junction in domain.junctions:
            if str(junction.x_rail_id) not in active_x_ids:
                raise ValueError(
                    f"Node {node_id!r} references unknown x rail {junction.x_rail_id!r}"
                )
            if str(junction.y_rail_id) not in active_y_ids:
                raise ValueError(
                    f"Node {node_id!r} references unknown y rail {junction.y_rail_id!r}"
                )


def _empty_domain_node_ids(domains: dict[NodeId, NodeDomain]) -> tuple[NodeId, ...]:
    return tuple(
        node_id
        for node_id, domain in domains.items()
        if not domain.junctions
    )


def _apply_tier_propagation(
    active_grid: ActiveGridState,
    domains: dict[NodeId, NodeDomain],
    node_metadata: dict[NodeId, NodePlacementMetadata],
) -> dict[NodeId, NodeDomain]:
    updated: dict[NodeId, NodeDomain] = {}
    for node_id, domain in domains.items():
        metadata = node_metadata.get(node_id)
        if metadata is None:
            updated[node_id] = domain
            continue

        if metadata.authored_tier_y_rail_id is not None:
            allowed_y_rail_ids = build_authored_tier_dom_y(
                active_grid,
                metadata.authored_tier_y_rail_id,
            )
        else:
            allowed_y_rail_ids = build_dynamic_dom_y(
                active_grid,
                metadata.allowed_y_rail_ids,
            )

        allowed_y_lookup = {str(rail_id) for rail_id in allowed_y_rail_ids}
        updated[node_id] = NodeDomain(
            node_id=domain.node_id,
            junctions=frozenset(
                junction
                for junction in domain.junctions
                if str(junction.y_rail_id) in allowed_y_lookup
            ),
        )

    return updated


def _apply_occupancy_propagation(
    domains: dict[NodeId, NodeDomain],
) -> dict[NodeId, NodeDomain]:
    singleton_junctions = {
        node_id: next(iter(domain.junctions))
        for node_id, domain in domains.items()
        if len(domain.junctions) == 1
    }

    updated: dict[NodeId, NodeDomain] = {}
    for node_id, domain in domains.items():
        junctions = set(domain.junctions)

        for other_node_id, occupied_junction in singleton_junctions.items():
            if other_node_id == node_id:
                continue

            junctions.discard(occupied_junction)

        updated[node_id] = NodeDomain(
            node_id=domain.node_id,
            junctions=frozenset(junctions),
        )

    return updated


def _one_gap_assignments(
    rail_count: int,
    node_count: int,
) -> tuple[tuple[int, ...], ...]:
    return tuple(
        assignment
        for assignment in combinations(range(rail_count), node_count)
        if all(
            assignment[index + 1] - assignment[index] >= (_SAFE_ONE_GAP + 1)
            for index in range(node_count - 1)
        )
    )


def _apply_ordered_row_propagation(
    active_grid: ActiveGridState,
    domains: dict[NodeId, NodeDomain],
    ordered_same_row_groups: Sequence[OrderedSameRowGroup],
) -> dict[NodeId, NodeDomain]:
    x_rail_ids = _ordered_active_x_rail_ids(active_grid)
    rail_count = len(x_rail_ids)
    y_rail_ids = tuple(
        rail.rail_id
        for rail in sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    )

    if not ordered_same_row_groups:
        return dict(domains)

    updated = dict(domains)
    nodes_in_groups: set[NodeId] = set()

    for row_group in ordered_same_row_groups:
        node_ids = row_group.ordered_node_ids
        node_count = len(node_ids)

        if rail_count != _SAFE_ORDERED_ROW_RAIL_COUNT or node_count not in _SAFE_ORDERED_ROW_NODE_COUNTS:
            raise NotImplementedError(
                "Only ordered same-row propagation for 3 or 4 nodes on 7 x rails is implemented"
            )

        for node_id in node_ids:
            if node_id not in updated:
                raise ValueError("ordered_same_row_groups references an unknown node id")
            if node_id in nodes_in_groups:
                raise ValueError("A node may not appear in multiple ordered same-row groups")
            nodes_in_groups.add(node_id)

        candidate_assignments = _one_gap_assignments(rail_count, node_count)
        valid_assignments: list[tuple[Junction, ...]] = []
        for y_rail_id in y_rail_ids:
            for assignment in candidate_assignments:
                junction_assignment = tuple(
                    Junction(
                        x_rail_id=x_rail_ids[assignment[position]],
                        y_rail_id=y_rail_id,
                    )
                    for position in range(node_count)
                )
                if all(
                    junction_assignment[position] in updated[node_id].junctions
                    for position, node_id in enumerate(node_ids)
                ):
                    valid_assignments.append(junction_assignment)

        for position, node_id in enumerate(node_ids):
            supported_junctions = frozenset(
                assignment[position]
                for assignment in valid_assignments
            )
            updated[node_id] = NodeDomain(
                node_id=updated[node_id].node_id,
                junctions=supported_junctions,
            )

    return updated


def propagate_domains(
    active_grid: ActiveGridState,
    domains: dict[NodeId, NodeDomain],
    node_metadata: Sequence[NodePlacementMetadata] = (),
    ordered_same_row_groups: Sequence[OrderedSameRowGroup] = (),
) -> PropagationResult:
    """Run frozen structural propagation to a fixed point.

    This function works only on already-built domains. It does not build new
    domains, perform screening, or route paths.
    """

    current_domains = dict(domains)
    metadata_by_node_id = _node_metadata_lookup(node_metadata)
    _validate_domains_on_active_grid(active_grid, current_domains)

    changed = True
    while changed:
        changed = False

        contradiction_node_ids = _empty_domain_node_ids(current_domains)
        if contradiction_node_ids:
            return PropagationResult(
                domains=current_domains,
                has_contradiction=True,
                contradiction_node_ids=contradiction_node_ids,
            )

        tier_domains = _apply_tier_propagation(active_grid, current_domains, metadata_by_node_id)
        if tier_domains != current_domains:
            current_domains = tier_domains
            changed = True

        contradiction_node_ids = _empty_domain_node_ids(current_domains)
        if contradiction_node_ids:
            return PropagationResult(
                domains=current_domains,
                has_contradiction=True,
                contradiction_node_ids=contradiction_node_ids,
            )

        row_domains = _apply_ordered_row_propagation(
            active_grid,
            current_domains,
            ordered_same_row_groups,
        )
        if row_domains != current_domains:
            current_domains = row_domains
            changed = True

        contradiction_node_ids = _empty_domain_node_ids(current_domains)
        if contradiction_node_ids:
            return PropagationResult(
                domains=current_domains,
                has_contradiction=True,
                contradiction_node_ids=contradiction_node_ids,
            )

        occupancy_domains = _apply_occupancy_propagation(current_domains)
        if occupancy_domains != current_domains:
            current_domains = occupancy_domains
            changed = True

    contradiction_node_ids = _empty_domain_node_ids(current_domains)
    return PropagationResult(
        domains=current_domains,
        has_contradiction=bool(contradiction_node_ids),
        contradiction_node_ids=contradiction_node_ids,
    )
