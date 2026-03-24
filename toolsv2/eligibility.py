"""Concrete v1 local candidate eligibility only.

This module filters one geometrically feasible candidate port at a time. It
must not perform adjacency discovery, geometry/build-feasibility checks,
global route correctness checks, router search, or route-commit behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from toolsv2.solver_common import (
    CandidateEligibility,
    FrontierContext,
    Junction,
    NeighborRelation,
    ObjectRef,
    PortId,
    PortRef,
    RouteRequirement,
    RouteRequirementSchemaView,
)
from toolsv2.solver_runtime import (
    RuntimeObjectSet,
    can_port_ref_accept_new_attachment,
    is_port_ref_usable,
)


@dataclass(frozen=True, slots=True)
class RouteRequirementPortAllowance:
    """Data-only per-object port allowance for one requirement kind."""

    object_ref: ObjectRef
    requirement_kind: str
    port_local_keys: tuple[PortId, ...]
    requirement_id: str | None = None

    def __post_init__(self) -> None:
        if not self.requirement_kind:
            raise ValueError("RouteRequirementPortAllowance.requirement_kind must not be empty")
        if self.requirement_id is not None and not self.requirement_id:
            raise ValueError("RouteRequirementPortAllowance.requirement_id must not be empty")
        if len(self.port_local_keys) != len(set(self.port_local_keys)):
            raise ValueError("RouteRequirementPortAllowance.port_local_keys must be unique")


@dataclass(frozen=True, slots=True)
class StaticRouteRequirementSchemaView:
    """Minimal data-only schema lookup for v1 route-requirement allowances."""

    source_allowances: tuple[RouteRequirementPortAllowance, ...] = ()
    sink_allowances: tuple[RouteRequirementPortAllowance, ...] = ()

    def __post_init__(self) -> None:
        source_keys = tuple(
            (allowance.object_ref, allowance.requirement_kind, allowance.requirement_id)
            for allowance in self.source_allowances
        )
        sink_keys = tuple(
            (allowance.object_ref, allowance.requirement_kind, allowance.requirement_id)
            for allowance in self.sink_allowances
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError(
                "StaticRouteRequirementSchemaView.source_allowances must be unique by object_ref, requirement_kind, and requirement_id"
            )
        if len(sink_keys) != len(set(sink_keys)):
            raise ValueError(
                "StaticRouteRequirementSchemaView.sink_allowances must be unique by object_ref, requirement_kind, and requirement_id"
            )

    def source_port_keys(
        self,
        object_ref: ObjectRef,
        route_requirement: RouteRequirement,
    ) -> tuple[PortId, ...]:
        fallback: tuple[PortId, ...] = ()
        for allowance in self.source_allowances:
            if (
                allowance.object_ref == object_ref
                and allowance.requirement_kind == route_requirement.requirement_kind
            ):
                if allowance.requirement_id == route_requirement.requirement_id:
                    return allowance.port_local_keys
                if allowance.requirement_id is None:
                    fallback = allowance.port_local_keys
        return fallback

    def sink_port_keys(
        self,
        object_ref: ObjectRef,
        route_requirement: RouteRequirement,
    ) -> tuple[PortId, ...]:
        fallback: tuple[PortId, ...] = ()
        for allowance in self.sink_allowances:
            if (
                allowance.object_ref == object_ref
                and allowance.requirement_kind == route_requirement.requirement_kind
            ):
                if allowance.requirement_id == route_requirement.requirement_id:
                    return allowance.port_local_keys
                if allowance.requirement_id is None:
                    fallback = allowance.port_local_keys
        return fallback


@dataclass(frozen=True, slots=True)
class V1CandidateEligibility:
    """Concrete v1 local candidate eligibility.

    This class owns only local candidate-port checks:
    - candidate existence/usability in current runtime state
    - source/sink object port allowance lookups
    - conservative acceptance of active intermediate junction ports

    TODO: multi-step tentative capacity accounting within a not-yet-committed route
    plan remains open. Current capacity checks are authoritative at commit and
    conservative against the current committed snapshot only.
    """

    def __call__(
        self,
        runtime_objects: RuntimeObjectSet,
        schema_view: RouteRequirementSchemaView,
        frontier_context: FrontierContext,
        neighbor_relation: NeighborRelation,
        route_requirement: RouteRequirement,
        candidate_port_ref: PortRef,
    ) -> bool:
        if not isinstance(runtime_objects, RuntimeObjectSet):
            raise TypeError("runtime_objects must be RuntimeObjectSet")
        if not isinstance(frontier_context, FrontierContext):
            raise TypeError("frontier_context must be FrontierContext")
        if not isinstance(neighbor_relation, NeighborRelation):
            raise TypeError("neighbor_relation must be NeighborRelation")
        if not isinstance(route_requirement, RouteRequirement):
            raise TypeError("route_requirement must be RouteRequirement")
        if not isinstance(candidate_port_ref, PortRef):
            raise TypeError("candidate_port_ref must be PortRef")

        current_object_ref = frontier_context.current_object_ref
        current_port_ref = frontier_context.current_port_ref
        if current_port_ref.owner_ref != current_object_ref:
            raise ValueError(
                "FrontierContext.current_port_ref must belong to FrontierContext.current_object_ref"
            )
        if neighbor_relation.from_object_ref != current_object_ref:
            raise ValueError(
                "NeighborRelation.from_object_ref must match FrontierContext.current_object_ref"
            )
        if candidate_port_ref.owner_ref != neighbor_relation.to_object_ref:
            return False

        try:
            if not is_port_ref_usable(runtime_objects, current_port_ref):
                return False
            if not is_port_ref_usable(runtime_objects, candidate_port_ref):
                return False
            if not can_port_ref_accept_new_attachment(runtime_objects, current_port_ref):
                return False
            if not can_port_ref_accept_new_attachment(runtime_objects, candidate_port_ref):
                return False
        except KeyError:
            return False

        candidate_owner_ref = candidate_port_ref.owner_ref
        candidate_port_key = candidate_port_ref.owner_local_key

        if candidate_owner_ref == route_requirement.sink_object_ref:
            return candidate_port_key in schema_view.sink_port_keys(
                candidate_owner_ref,
                route_requirement,
            )
        if candidate_owner_ref == route_requirement.source_object_ref:
            return candidate_port_key in schema_view.source_port_keys(
                candidate_owner_ref,
                route_requirement,
            )
        if isinstance(candidate_owner_ref, Junction):
            return True
        return False


def build_v1_candidate_eligibility() -> CandidateEligibility:
    """Return the concrete v1 local candidate eligibility callable."""

    return V1CandidateEligibility()
