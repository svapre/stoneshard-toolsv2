"""Initial raw-domain construction from frozen hard constraints only.

This module builds initial explicit legal-junction sets from the current
active grid and explicit node metadata. It does not perform propagation,
screening, reachability checks, or exact routing.

Implemented subset:

- authored-tier nodes with singleton-y junction sets
- dynamic nodes with junction sets from currently active allowed y rails
- unconstrained ``Dom_x`` as an internal helper over all active x rails
- ordered same-row ``Dom_x`` from the current layout-profile minimum spacing
  rule on the active x rails

Open items such as broader ``Dom_x`` policy beyond the frozen hard constraints,
general row-spacing policy beyond the current layout-profile minimum-gap rule, and
propagation-side pruning beyond the current subset remain intentionally open.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from toolsv2.solver_types import (
    ActiveGridState,
    Junction,
    LogicalXRailId,
    LogicalYRailId,
    NodeDomain,
    NodeId,
)


_DEFAULT_MINIMUM_SAME_ROW_GAP = 1


@dataclass(frozen=True, slots=True)
class NodePlacementMetadata:
    """Minimal metadata for initial domain construction.

    A node is treated as tier/authored when ``authored_tier_y_rail_id`` is set.
    Otherwise it is treated as dynamic/implied for ``Dom_y`` purposes.

    This type must not assume propagation, routing, or screening outcomes.
    """

    node_id: NodeId
    authored_tier_y_rail_id: LogicalYRailId | None = None
    allowed_y_rail_ids: tuple[LogicalYRailId, ...] | None = None

    def __post_init__(self) -> None:
        if self.authored_tier_y_rail_id is not None and self.allowed_y_rail_ids is not None:
            raise ValueError(
                "NodePlacementMetadata must not set both authored_tier_y_rail_id and allowed_y_rail_ids"
            )


@dataclass(frozen=True, slots=True)
class OrderedSameRowGroup:
    """Explicit same-row order metadata for current hard-constraint handling.

    Current raw-domain and propagation support use row order plus the active
    layout-profile minimum same-row spacing hard constraint on the current
    active x rails.
    Broader row-shape policy remains open.
    """

    ordered_node_ids: tuple[NodeId, ...]


def _ordered_x_rail_ids(active_grid: ActiveGridState) -> tuple[LogicalXRailId, ...]:
    return tuple(
        rail.rail_id
        for rail in sorted(active_grid.x_rails, key=lambda rail: rail.order)
    )


def _active_y_rail_lookup(active_grid: ActiveGridState) -> dict[str, str]:
    return {str(rail.rail_id): rail.kind for rail in active_grid.y_rails}


def build_authored_tier_dom_y(
    active_grid: ActiveGridState,
    authored_tier_y_rail_id: LogicalYRailId,
) -> tuple[LogicalYRailId, ...]:
    """Return the singleton authored-tier ``Dom_y``.

    The referenced y rail must exist on the active grid and must be an authored
    rail. Invalid authored-tier references fail loudly.
    """

    y_lookup = _active_y_rail_lookup(active_grid)
    rail_kind = y_lookup.get(str(authored_tier_y_rail_id))
    if rail_kind is None:
        raise ValueError("Authored tier y rail is not present on the active grid")
    if rail_kind != "authored":
        raise ValueError("Authored tier y rail must reference an authored rail")
    return (authored_tier_y_rail_id,)


def build_dynamic_dom_y(
    active_grid: ActiveGridState,
    allowed_y_rail_ids: Sequence[LogicalYRailId] | None = None,
) -> tuple[LogicalYRailId, ...]:
    """Return ``Dom_y`` for a dynamic/implied node from the current active grid.

    When ``allowed_y_rail_ids`` is omitted, all active logical y rails are
    allowed. When supplied, the domain is the active-grid intersection only.
    """

    active_y_rail_ids = tuple(rail.rail_id for rail in active_grid.y_rails)
    if allowed_y_rail_ids is None:
        return active_y_rail_ids

    allowed_lookup = {str(rail_id) for rail_id in allowed_y_rail_ids}
    return tuple(
        rail_id
        for rail_id in active_y_rail_ids
        if str(rail_id) in allowed_lookup
    )


def enumerate_minimum_gap_ordered_row_assignments(
    x_rail_ids: Sequence[LogicalXRailId],
    node_count: int,
    minimum_same_row_gap: int = _DEFAULT_MINIMUM_SAME_ROW_GAP,
) -> tuple[tuple[LogicalXRailId, ...], ...]:
    ordered_x_rail_ids = tuple(x_rail_ids)
    if minimum_same_row_gap < 0:
        raise ValueError("minimum_same_row_gap must be non-negative")
    return tuple(
        tuple(ordered_x_rail_ids[rail_index] for rail_index in assignment)
        for assignment in combinations(range(len(ordered_x_rail_ids)), node_count)
        if all(
            assignment[index + 1] - assignment[index] >= (minimum_same_row_gap + 1)
            for index in range(node_count - 1)
        )
    )


def build_ordered_same_row_dom_x(
    active_grid: ActiveGridState,
    ordered_node_ids: Sequence[NodeId],
    minimum_same_row_gap: int = _DEFAULT_MINIMUM_SAME_ROW_GAP,
) -> dict[NodeId, tuple[LogicalXRailId, ...]]:
    """Build ``Dom_x`` for ordered same-row groups under the minimum-gap rule."""

    x_rail_ids = _ordered_x_rail_ids(active_grid)
    node_ids = tuple(ordered_node_ids)
    node_count = len(node_ids)
    assignments = enumerate_minimum_gap_ordered_row_assignments(
        x_rail_ids,
        node_count,
        minimum_same_row_gap=minimum_same_row_gap,
    )

    domains_by_position = []
    for position in range(node_count):
        supported_x_rail_ids = {
            assignment[position]
            for assignment in assignments
        }
        domains_by_position.append(
            tuple(
                x_rail_id
                for x_rail_id in x_rail_ids
                if x_rail_id in supported_x_rail_ids
            )
        )

    return {
        node_id: domains_by_position[position]
        for position, node_id in enumerate(node_ids)
    }


def build_raw_domains(
    active_grid: ActiveGridState,
    node_metadata: Sequence[NodePlacementMetadata],
    ordered_same_row_groups: Sequence[OrderedSameRowGroup] = (),
    minimum_same_row_gap: int = _DEFAULT_MINIMUM_SAME_ROW_GAP,
) -> dict[NodeId, NodeDomain]:
    """Build raw node domains as explicit legal-junction sets.

    This function does not perform propagation or candidate elimination beyond
    the directly encoded hard constraints in its inputs.
    """

    metadata_by_node_id = {metadata.node_id: metadata for metadata in node_metadata}
    if len(metadata_by_node_id) != len(tuple(node_metadata)):
        raise ValueError("node_metadata contains duplicate node ids")
    if minimum_same_row_gap < 0:
        raise ValueError("minimum_same_row_gap must be non-negative")

    all_x_rail_ids = _ordered_x_rail_ids(active_grid)
    x_domains_by_node_id: dict[NodeId, tuple[LogicalXRailId, ...]] = {
        node_id: all_x_rail_ids
        for node_id in metadata_by_node_id
    }

    nodes_with_row_domains: set[NodeId] = set()
    for row_group in ordered_same_row_groups:
        for node_id in row_group.ordered_node_ids:
            if node_id not in metadata_by_node_id:
                raise ValueError("ordered_same_row_groups references an unknown node id")
            if node_id in nodes_with_row_domains:
                raise ValueError("A node may not appear in multiple ordered same-row groups")

        row_x_domains = build_ordered_same_row_dom_x(
            active_grid,
            row_group.ordered_node_ids,
            minimum_same_row_gap=minimum_same_row_gap,
        )
        x_domains_by_node_id.update(row_x_domains)
        nodes_with_row_domains.update(row_group.ordered_node_ids)

    raw_domains: dict[NodeId, NodeDomain] = {}
    for node_id, metadata in metadata_by_node_id.items():
        if metadata.authored_tier_y_rail_id is not None:
            y_domain = build_authored_tier_dom_y(active_grid, metadata.authored_tier_y_rail_id)
        else:
            y_domain = build_dynamic_dom_y(active_grid, metadata.allowed_y_rail_ids)

        raw_domains[node_id] = NodeDomain(
            node_id=node_id,
            junctions=frozenset(
                Junction(x_rail_id=x_rail_id, y_rail_id=y_rail_id)
                for x_rail_id in x_domains_by_node_id[node_id]
                for y_rail_id in y_domain
            ),
        )

    return raw_domains
