"""Concrete v1 adjacency discovery over current runtime objects.

This module implements only neutral adjacency discovery. It must not perform
geometry/build-feasibility checks, candidate eligibility checks, router
search, pathfinding, or route-commit behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from toolsv2.solver_common import (
    ActiveGridState,
    AdjacencyFinder,
    CardinalDirection,
    FrontierContext,
    Junction,
    NeighborRelation,
    ObjectRef,
    PortId,
)
from toolsv2.solver_runtime import (
    RuntimeJunction,
    RuntimeNode,
    RuntimeObjectSet,
    is_object_ref_active,
    is_port_ref_usable,
)
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    PortGeometrySpec,
    VisualProfileCatalog,
    build_v1_plain_junction_visual_profile_catalog,
)


LOCAL_SAME_OBJECT_RELATION_KIND = "same_object_local"
CROSS_OBJECT_BOUNDARY_RELATION_KIND = "cross_object_boundary"

_OPPOSITE_BOUNDARY_DIRECTION: dict[str, str] = {
    "north": "south",
    "south": "north",
    "west": "east",
    "east": "west",
}


def _junction_lookup(runtime_objects: RuntimeObjectSet) -> dict[Junction, RuntimeJunction]:
    return {
        junction.junction_id: junction
        for junction in runtime_objects.junctions
    }


def _node_lookup(runtime_objects: RuntimeObjectSet) -> dict[ObjectRef, RuntimeNode]:
    return {
        node.node_id: node
        for node in runtime_objects.nodes
    }


def _build_geometry_profile_for_object(
    visual_profile_catalog: VisualProfileCatalog,
    runtime_objects: RuntimeObjectSet,
    object_ref: ObjectRef,
) -> BuildGeometryProfile | None:
    if isinstance(object_ref, Junction):
        runtime_junction = _junction_lookup(runtime_objects).get(object_ref)
        if runtime_junction is None:
            raise KeyError(f"Unknown runtime junction: {object_ref}")
        profile_key = runtime_junction.render_profile.profile_key
    else:
        runtime_node = _node_lookup(runtime_objects).get(object_ref)
        if runtime_node is None:
            raise KeyError(f"Unknown runtime node: {object_ref}")
        profile_key = runtime_node.render_profile.profile_key

    if profile_key is None:
        return None
    return visual_profile_catalog.build_geometry_profile(profile_key)


def _port_geometry_by_id(profile: BuildGeometryProfile) -> dict[PortId, PortGeometrySpec]:
    return {
        port.port_id: port
        for port in profile.ports
    }


def _anchor_junction_for_object(
    runtime_objects: RuntimeObjectSet,
    object_ref: ObjectRef,
) -> Junction | None:
    if isinstance(object_ref, Junction):
        return object_ref

    runtime_node = _node_lookup(runtime_objects).get(object_ref)
    if runtime_node is None:
        raise KeyError(f"Unknown runtime node: {object_ref}")
    return runtime_node.current_junction_id


def _has_local_transition_from_port(
    profile: BuildGeometryProfile,
    current_port_id: PortId,
) -> bool:
    return any(
        transition.from_port_id == current_port_id
        for transition in profile.internal_transitions
    )


def _has_boundary_port(
    profile: BuildGeometryProfile,
    attach_direction: CardinalDirection,
) -> bool:
    return any(
        port.attach_direction == attach_direction
        for port in profile.ports
    )


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
    """Concrete v1 adjacency finder for current grid-bound runtime objects.

    This finder returns only neutral object relations. It does not select
    candidate ports, evaluate logical compatibility, or perform router search.
    """

    active_grid: ActiveGridState
    visual_profile_catalog: VisualProfileCatalog = field(
        default_factory=build_v1_plain_junction_visual_profile_catalog
    )

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

        if current_port_ref.owner_ref != current_object_ref:
            raise ValueError(
                "FrontierContext.current_port_ref must belong to FrontierContext.current_object_ref"
            )

        if not is_object_ref_active(runtime_objects, current_object_ref):
            return ()
        if not is_port_ref_usable(runtime_objects, current_port_ref):
            return ()

        current_profile = _build_geometry_profile_for_object(
            self.visual_profile_catalog,
            runtime_objects,
            current_object_ref,
        )
        if current_profile is None:
            return ()

        current_port_geometry = _port_geometry_by_id(current_profile).get(
            current_port_ref.owner_local_key
        )
        if current_port_geometry is None:
            return ()

        approach_direction = current_port_geometry.attach_direction
        relations: list[NeighborRelation] = []

        if _has_local_transition_from_port(current_profile, current_port_ref.owner_local_key):
            relations.append(
                NeighborRelation(
                    from_object_ref=current_object_ref,
                    to_object_ref=current_object_ref,
                    relation_kind=LOCAL_SAME_OBJECT_RELATION_KIND,
                    approach_direction=approach_direction,
                )
            )

        anchor_junction_id = _anchor_junction_for_object(runtime_objects, current_object_ref)
        if anchor_junction_id is None:
            return tuple(relations)

        adjacent_junction_id = _adjacent_junction_for_direction(
            active_grid=self.active_grid,
            current_junction_id=anchor_junction_id,
            direction=approach_direction,
        )
        if adjacent_junction_id is None:
            return tuple(relations)

        junction_lookup = _junction_lookup(runtime_objects)
        adjacent_junction = junction_lookup.get(adjacent_junction_id)
        if adjacent_junction is None:
            return tuple(relations)

        opposite_direction = _OPPOSITE_BOUNDARY_DIRECTION[approach_direction]

        if not isinstance(current_object_ref, Junction):
            if adjacent_junction.occupying_node_id is not None:
                target_object_ref = adjacent_junction.occupying_node_id
                if not is_object_ref_active(runtime_objects, target_object_ref):
                    return tuple(relations)
                target_profile = _build_geometry_profile_for_object(
                    self.visual_profile_catalog,
                    runtime_objects,
                    target_object_ref,
                )
                if target_profile is None or not _has_boundary_port(target_profile, opposite_direction):
                    return tuple(relations)
                relations.append(
                    NeighborRelation(
                        from_object_ref=current_object_ref,
                        to_object_ref=target_object_ref,
                        relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                        approach_direction=approach_direction,
                    )
                )
                return tuple(relations)

            if not is_object_ref_active(runtime_objects, adjacent_junction_id):
                return tuple(relations)
            target_profile = _build_geometry_profile_for_object(
                self.visual_profile_catalog,
                runtime_objects,
                adjacent_junction_id,
            )
            if target_profile is None or not _has_boundary_port(target_profile, opposite_direction):
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

        if adjacent_junction.occupying_node_id is not None:
            target_object_ref = adjacent_junction.occupying_node_id
            if not is_object_ref_active(runtime_objects, target_object_ref):
                return tuple(relations)
            target_profile = _build_geometry_profile_for_object(
                self.visual_profile_catalog,
                runtime_objects,
                target_object_ref,
            )
            if target_profile is None or not _has_boundary_port(target_profile, opposite_direction):
                return tuple(relations)
            relations.append(
                NeighborRelation(
                    from_object_ref=current_object_ref,
                    to_object_ref=target_object_ref,
                    relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                    approach_direction=approach_direction,
                )
            )
            return tuple(relations)

        if not is_object_ref_active(runtime_objects, adjacent_junction_id):
            return tuple(relations)
        target_profile = _build_geometry_profile_for_object(
            self.visual_profile_catalog,
            runtime_objects,
            adjacent_junction_id,
        )
        if target_profile is None or not _has_boundary_port(target_profile, opposite_direction):
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
    visual_profile_catalog: VisualProfileCatalog | None = None,
) -> AdjacencyFinder:
    """Bind the current active grid into the current v1 adjacency finder."""

    if visual_profile_catalog is None:
        return V1JunctionAdjacencyFinder(active_grid=active_grid)
    return V1JunctionAdjacencyFinder(
        active_grid=active_grid,
        visual_profile_catalog=visual_profile_catalog,
    )
