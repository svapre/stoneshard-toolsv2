"""Concrete v1 adjacency discovery over runtime junctions only.

This module implements only neutral adjacency discovery. It must not perform
geometry/build-feasibility checks, candidate eligibility checks, router
search, pathfinding, or route-commit behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from toolsv2.solver_common import (
    ActiveGridState,
    AdjacencyFinder,
    CardinalDirection,
    FrontierContext,
    Junction,
    NeighborRelation,
    PortId,
)
from toolsv2.solver_runtime import RuntimeJunction, RuntimeObjectSet, is_object_ref_active, is_port_ref_usable


LOCAL_SAME_OBJECT_RELATION_KIND = "same_object_local"
CROSS_OBJECT_BOUNDARY_RELATION_KIND = "cross_object_boundary"

_CARDINAL_PORT_IDS: dict[PortId, CardinalDirection] = {
    PortId("north"): "north",
    PortId("south"): "south",
    PortId("west"): "west",
    PortId("east"): "east",
}


def _junction_lookup(runtime_objects: RuntimeObjectSet) -> dict[Junction, RuntimeJunction]:
    return {
        junction.junction_id: junction
        for junction in runtime_objects.junctions
    }


def _junction_port_direction(port_local_key: PortId) -> CardinalDirection:
    direction = _CARDINAL_PORT_IDS.get(port_local_key)
    if direction is None:
        raise NotImplementedError(
            "V1JunctionAdjacencyFinder supports only cardinal junction-port local keys"
        )
    return direction


def _is_plain_junction(runtime_junction: RuntimeJunction) -> bool:
    return {
        port.port_ref.owner_local_key
        for port in runtime_junction.ports
    } == set(_CARDINAL_PORT_IDS)


def _adjacent_junction_for_direction(
    active_grid: ActiveGridState,
    current_junction_id: Junction,
    direction: CardinalDirection,
) -> Junction | None:
    ordered_x_rail_ids = tuple(
        rail.rail_id
        for rail in sorted(active_grid.x_rails, key=lambda rail: rail.order)
    )
    ordered_y_rail_ids = tuple(
        rail.rail_id
        for rail in sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    )

    try:
        x_index = ordered_x_rail_ids.index(current_junction_id.x_rail_id)
        y_index = ordered_y_rail_ids.index(current_junction_id.y_rail_id)
    except ValueError as exc:
        raise KeyError(
            "Frontier junction is not present on the active grid"
        ) from exc

    if direction == "north":
        if y_index == 0:
            return None
        return Junction(
            x_rail_id=current_junction_id.x_rail_id,
            y_rail_id=ordered_y_rail_ids[y_index - 1],
        )
    if direction == "south":
        if y_index >= len(ordered_y_rail_ids) - 1:
            return None
        return Junction(
            x_rail_id=current_junction_id.x_rail_id,
            y_rail_id=ordered_y_rail_ids[y_index + 1],
        )
    if direction == "west":
        if x_index == 0:
            return None
        return Junction(
            x_rail_id=ordered_x_rail_ids[x_index - 1],
            y_rail_id=current_junction_id.y_rail_id,
        )
    if direction == "east":
        if x_index >= len(ordered_x_rail_ids) - 1:
            return None
        return Junction(
            x_rail_id=ordered_x_rail_ids[x_index + 1],
            y_rail_id=current_junction_id.y_rail_id,
        )
    raise AssertionError(f"Unhandled cardinal direction: {direction}")


@dataclass(frozen=True, slots=True)
class V1JunctionAdjacencyFinder:
    """Concrete v1 adjacency finder for runtime junction frontier contexts only.

    This finder returns only neutral object relations. It does not select
    candidate ports, evaluate logical compatibility, or perform router search.
    """

    active_grid: ActiveGridState

    def __call__(
        self,
        runtime_objects: RuntimeObjectSet,
        frontier_context: FrontierContext,
    ) -> tuple[NeighborRelation, ...]:
        if not isinstance(runtime_objects, RuntimeObjectSet):
            raise TypeError("runtime_objects must be RuntimeObjectSet")
        if not isinstance(frontier_context, FrontierContext):
            raise TypeError("frontier_context must be FrontierContext")

        current_object_ref = frontier_context.current_object_ref
        current_port_ref = frontier_context.current_port_ref

        if not isinstance(current_object_ref, Junction):
            raise NotImplementedError(
                "V1JunctionAdjacencyFinder supports junction frontier objects only"
            )
        if current_port_ref.owner_ref != current_object_ref:
            raise ValueError(
                "FrontierContext.current_port_ref must belong to FrontierContext.current_object_ref"
            )

        junction_lookup = _junction_lookup(runtime_objects)
        current_junction = junction_lookup.get(current_object_ref)
        if current_junction is None:
            raise KeyError(f"Unknown frontier junction: {current_object_ref}")

        if not is_object_ref_active(runtime_objects, current_object_ref):
            return ()
        if not is_port_ref_usable(runtime_objects, current_port_ref):
            return ()

        approach_direction = _junction_port_direction(current_port_ref.owner_local_key)
        relations: list[NeighborRelation] = []

        if _is_plain_junction(current_junction) and len(current_junction.ports) > 1:
            relations.append(
                NeighborRelation(
                    from_object_ref=current_object_ref,
                    to_object_ref=current_object_ref,
                    relation_kind=LOCAL_SAME_OBJECT_RELATION_KIND,
                    approach_direction=approach_direction,
                )
            )

        adjacent_junction_id = _adjacent_junction_for_direction(
            active_grid=self.active_grid,
            current_junction_id=current_object_ref,
            direction=approach_direction,
        )
        if adjacent_junction_id is None:
            return tuple(relations)

        adjacent_junction = junction_lookup.get(adjacent_junction_id)
        if adjacent_junction is None:
            return tuple(relations)
        if not is_object_ref_active(runtime_objects, adjacent_junction_id):
            return tuple(relations)

        relations.append(
            NeighborRelation(
                from_object_ref=current_object_ref,
                to_object_ref=adjacent_junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction=approach_direction,
            )
        )
        return tuple(relations)


def build_v1_junction_adjacency_finder(
    active_grid: ActiveGridState,
) -> AdjacencyFinder:
    """Bind the current active grid into a concrete v1 junction adjacency finder."""

    return V1JunctionAdjacencyFinder(active_grid=active_grid)
