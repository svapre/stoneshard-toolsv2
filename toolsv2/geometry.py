"""Concrete v1 build-geometry feasibility over runtime junctions only.

This module implements only physical/build-geometric candidate-port discovery.
It must not perform logical eligibility checks, route-requirement checks,
router search, pathfinding, or route-commit behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from toolsv2.adjacency import (
    CROSS_OBJECT_BOUNDARY_RELATION_KIND,
    LOCAL_SAME_OBJECT_RELATION_KIND,
)
from toolsv2.solver_common import (
    FrontierContext,
    GeometryBuildFeasibility,
    Junction,
    NeighborRelation,
    PortId,
    PortRef,
)
from toolsv2.solver_runtime import (
    RuntimeJunction,
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


def _build_geometry_profile_for_junction(
    visual_profile_catalog: VisualProfileCatalog,
    runtime_junction: RuntimeJunction,
) -> BuildGeometryProfile:
    profile_key = runtime_junction.render_profile.profile_key
    if profile_key is None:
        raise NotImplementedError(
            "V1JunctionGeometryBuildFeasibility requires junction render_profile.profile_key "
            "with build geometry data"
        )
    return visual_profile_catalog.build_geometry_profile(profile_key)


def _port_geometry_by_id(profile: BuildGeometryProfile) -> dict[PortId, PortGeometrySpec]:
    return {
        port.port_id: port
        for port in profile.ports
    }


@dataclass(frozen=True, slots=True)
class V1JunctionGeometryBuildFeasibility:
    """Concrete v1 geometry/build-feasibility for junction frontier contexts.

    This class returns only physically/build-feasible target ports in one
    local step. It does not inspect route requirements or semantic port roles.
    """

    visual_profile_catalog: VisualProfileCatalog = field(
        default_factory=build_v1_plain_junction_visual_profile_catalog
    )

    def __call__(
        self,
        runtime_objects: RuntimeObjectSet,
        frontier_context: FrontierContext,
        neighbor_relation: NeighborRelation,
    ) -> tuple[PortRef, ...]:
        if not isinstance(runtime_objects, RuntimeObjectSet):
            raise TypeError("runtime_objects must be RuntimeObjectSet")
        if not isinstance(frontier_context, FrontierContext):
            raise TypeError("frontier_context must be FrontierContext")
        if not isinstance(neighbor_relation, NeighborRelation):
            raise TypeError("neighbor_relation must be NeighborRelation")

        current_object_ref = frontier_context.current_object_ref
        current_port_ref = frontier_context.current_port_ref
        if not isinstance(current_object_ref, Junction):
            raise NotImplementedError(
                "V1JunctionGeometryBuildFeasibility supports junction frontier objects only"
            )
        if current_port_ref.owner_ref != current_object_ref:
            raise ValueError(
                "FrontierContext.current_port_ref must belong to FrontierContext.current_object_ref"
            )
        if neighbor_relation.from_object_ref != current_object_ref:
            raise ValueError(
                "NeighborRelation.from_object_ref must match FrontierContext.current_object_ref"
            )

        junction_lookup = _junction_lookup(runtime_objects)
        current_junction = junction_lookup.get(current_object_ref)
        if current_junction is None:
            raise KeyError(f"Unknown frontier junction: {current_object_ref}")
        if not is_object_ref_active(runtime_objects, current_object_ref):
            return ()
        if not is_port_ref_usable(runtime_objects, current_port_ref):
            return ()
        current_profile = _build_geometry_profile_for_junction(
            self.visual_profile_catalog,
            current_junction,
        )
        current_port_geometry = _port_geometry_by_id(current_profile).get(
            current_port_ref.owner_local_key
        )
        if current_port_geometry is None:
            raise KeyError(
                f"Current port is missing from build geometry profile: {current_port_ref.owner_local_key}"
            )

        target_object_ref = neighbor_relation.to_object_ref
        if not isinstance(target_object_ref, Junction):
            raise NotImplementedError(
                "V1JunctionGeometryBuildFeasibility supports junction target objects only"
            )
        target_junction = junction_lookup.get(target_object_ref)
        if target_junction is None:
            raise KeyError(f"Unknown target junction: {target_object_ref}")
        if not is_object_ref_active(runtime_objects, target_object_ref):
            return ()
        target_profile = _build_geometry_profile_for_junction(
            self.visual_profile_catalog,
            target_junction,
        )
        target_port_geometry_by_id = _port_geometry_by_id(target_profile)

        if neighbor_relation.relation_kind == LOCAL_SAME_OBJECT_RELATION_KIND:
            if target_object_ref != current_object_ref:
                raise ValueError(
                    "same_object_local relation must target the same object as the frontier"
                )
            allowed_target_port_ids = {
                transition.to_port_id
                for transition in current_profile.internal_transitions
                if transition.from_port_id == current_port_ref.owner_local_key
            }
            return tuple(
                port.port_ref
                for port in target_junction.ports
                if port.port_ref.owner_local_key in allowed_target_port_ids
            )

        if neighbor_relation.relation_kind == CROSS_OBJECT_BOUNDARY_RELATION_KIND:
            if current_port_geometry.attach_direction != neighbor_relation.approach_direction:
                return ()
            opposite_direction = _OPPOSITE_BOUNDARY_DIRECTION.get(
                neighbor_relation.approach_direction
            )
            if opposite_direction is None:
                raise NotImplementedError(
                    "V1JunctionGeometryBuildFeasibility supports only cardinal approach directions"
                )
            current_connection_families = set(current_port_geometry.connection_family_keys)
            return tuple(
                port.port_ref
                for port in target_junction.ports
                if (
                    port.port_ref.owner_local_key in target_port_geometry_by_id
                    and target_port_geometry_by_id[port.port_ref.owner_local_key].attach_direction
                    == opposite_direction
                    and bool(
                        current_connection_families.intersection(
                            target_port_geometry_by_id[
                                port.port_ref.owner_local_key
                            ].connection_family_keys
                        )
                    )
                )
            )

        raise NotImplementedError(
            "V1JunctionGeometryBuildFeasibility does not support this relation_kind"
        )


def build_v1_junction_geometry_build_feasibility(
    visual_profile_catalog: VisualProfileCatalog | None = None,
) -> GeometryBuildFeasibility:
    """Return the concrete v1 geometry/build-feasibility callable."""

    if visual_profile_catalog is None:
        return V1JunctionGeometryBuildFeasibility()
    return V1JunctionGeometryBuildFeasibility(
        visual_profile_catalog=visual_profile_catalog,
    )
