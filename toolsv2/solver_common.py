"""Shared primitive solver types.

This module contains stable ids, logical grid primitives, and core solver
state that are shared by schema and runtime layers. It must not embed schema-
specific object behavior or runtime routing semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Literal, NewType, Protocol


if TYPE_CHECKING:
    from toolsv2.solver_runtime import RuntimeObjectSet


ScalarValue = str | int | float | bool | None
Attributes = tuple[tuple[str, ScalarValue], ...]
CardinalDirection = Literal["north", "south", "west", "east"]
YRailKind = Literal["authored", "dynamic"]
EdgeScope = Literal["internal", "external"]
EdgeTraversalMode = Literal["bidirectional", "a_to_b", "b_to_a"]

LogicalXRailId = NewType("LogicalXRailId", str)
LogicalYRailId = NewType("LogicalYRailId", str)
BandId = NewType("BandId", str)
NodeId = NewType("NodeId", str)
PortId = NewType("PortId", str)
PortEdgeId = NewType("PortEdgeId", str)
RenderProfileKey = NewType("RenderProfileKey", str)


def _ensure_unique_strings(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _ensure_unique_hashables(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _ensure_unique_keys(label: str, values: Attributes) -> None:
    keys = tuple(key for key, _ in values)
    _ensure_unique_strings(label, keys)


@dataclass(frozen=True, slots=True)
class LogicalXRail:
    """A logical x rail in ordered solver space."""

    rail_id: LogicalXRailId
    order: int

    def __post_init__(self) -> None:
        if self.order < 0:
            raise ValueError("LogicalXRail.order must be non-negative")


@dataclass(frozen=True, slots=True)
class LogicalYRail:
    """A logical y rail in ordered solver space."""

    rail_id: LogicalYRailId
    logical_rank: Fraction
    kind: YRailKind
    authored_tier_index: int | None = None
    band_id: BandId | None = None

    def __post_init__(self) -> None:
        if self.kind == "authored":
            if self.authored_tier_index is None:
                raise ValueError("Authored y rails require authored_tier_index")
            if self.band_id is not None:
                raise ValueError("Authored y rails must not belong to a band")
            if self.logical_rank.denominator != 1:
                raise ValueError("Authored y rails must use integral logical_rank")
        else:
            if self.band_id is None:
                raise ValueError("Dynamic y rails require band_id")
            if self.authored_tier_index is not None:
                raise ValueError("Dynamic y rails must not declare authored_tier_index")


@dataclass(frozen=True, slots=True)
class Junction:
    """A single grid intersection at one x rail and one y rail."""

    x_rail_id: LogicalXRailId
    y_rail_id: LogicalYRailId


ObjectRef = NodeId | Junction


@dataclass(frozen=True, slots=True)
class PortRef:
    """A stable owner-scoped reference to a port.

    Port identity is ``(owner_ref, owner_local_key)``. The graph stores
    ``PortRef`` values rather than owning port objects directly.
    """

    owner_ref: ObjectRef
    owner_local_key: PortId

    def __post_init__(self) -> None:
        if not isinstance(self.owner_ref, (str, Junction)):
            raise TypeError("PortRef.owner_ref must be a node id or Junction")


@dataclass(frozen=True, slots=True)
class EntryContext:
    """Derived routing state for entry-conditioned reachability only.

    ``incoming_edge_id`` is ``None`` for a route-origin/start context. This is
    not a built object and must not embed search policy or route goals.
    """

    current_port_ref: PortRef
    incoming_edge_id: PortEdgeId | None = None


@dataclass(frozen=True, slots=True)
class FrontierContext:
    """The current neutral search position for routing-layer contracts only.

    This record carries only the current object and current port. It must not
    carry target semantics, geometry results, or eligibility state.
    """

    current_object_ref: ObjectRef
    current_port_ref: PortRef


@dataclass(frozen=True, slots=True)
class NeighborRelation:
    """A neutral adjacency fact between two objects or locations.

    ``relation_kind`` is an opaque neutral label. It must not encode route
    semantics, eligibility, or geometry results.
    """

    from_object_ref: ObjectRef
    to_object_ref: ObjectRef
    relation_kind: str
    approach_direction: CardinalDirection


@dataclass(frozen=True, slots=True)
class RouteRequirement:
    """Minimal object-level routing intent for v1 candidate eligibility."""

    requirement_id: str
    source_object_ref: ObjectRef
    sink_object_ref: ObjectRef
    requirement_kind: str
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if not self.requirement_id:
            raise ValueError("RouteRequirement.requirement_id must not be empty")
        if not self.requirement_kind:
            raise ValueError("RouteRequirement.requirement_kind must not be empty")
        _ensure_unique_keys("RouteRequirement.attributes", self.attributes)


class AdjacencyFinder(Protocol):
    """Thin callable contract for neutral adjacency discovery only."""

    def __call__(
        self,
        runtime_objects: "RuntimeObjectSet",
        frontier_context: FrontierContext,
    ) -> tuple[NeighborRelation, ...]:
        """Return neutral neighbor relations without feasibility or logic checks."""


class GeometryBuildFeasibility(Protocol):
    """Thin callable contract for physical/build-geometric port feasibility only."""

    def __call__(
        self,
        runtime_objects: "RuntimeObjectSet",
        frontier_context: FrontierContext,
        neighbor_relation: NeighborRelation,
    ) -> tuple[PortRef, ...]:
        """Return candidate ports that are physically feasible for this relation."""


class RouteRequirementSchemaView(Protocol):
    """Thin data-only lookup surface for route-requirement port allowances."""

    def source_port_keys(
        self,
        object_ref: ObjectRef,
        route_requirement: RouteRequirement,
    ) -> tuple[PortId, ...]:
        """Return schema-declared source-eligible local port keys for this requirement."""

    def sink_port_keys(
        self,
        object_ref: ObjectRef,
        route_requirement: RouteRequirement,
    ) -> tuple[PortId, ...]:
        """Return schema-declared sink-eligible local port keys for this requirement."""


class CandidateEligibility(Protocol):
    """Thin callable contract for logical/runtime candidate-port filtering only."""

    def __call__(
        self,
        runtime_objects: "RuntimeObjectSet",
        schema_view: RouteRequirementSchemaView,
        frontier_context: FrontierContext,
        neighbor_relation: NeighborRelation,
        route_requirement: RouteRequirement,
        candidate_port_ref: PortRef,
    ) -> bool:
        """Return whether one candidate port is eligible for the current route."""


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Configurable routing policy data only."""

    policy_id: str
    rule_values: Attributes = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("RoutingPolicy.policy_id must not be empty")
        _ensure_unique_keys("RoutingPolicy.rule_values", self.rule_values)
        _ensure_unique_keys("RoutingPolicy.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class NodeDomain:
    """The pre-routing domain for one node."""

    node_id: NodeId
    junctions: frozenset[Junction]

    def __post_init__(self) -> None:
        if not isinstance(self.junctions, frozenset):
            raise TypeError("NodeDomain.junctions must be a frozenset[Junction]")
        for junction in self.junctions:
            if not isinstance(junction, Junction):
                raise TypeError("NodeDomain.junctions must contain Junction values")


@dataclass(frozen=True, slots=True)
class YRailBandState:
    """A band between two authored y rails."""

    band_id: BandId
    upper_authored_rail_id: LogicalYRailId
    lower_authored_rail_id: LogicalYRailId
    dynamic_rail_ids: tuple[LogicalYRailId, ...] = ()

    def __post_init__(self) -> None:
        if self.upper_authored_rail_id == self.lower_authored_rail_id:
            raise ValueError("YRailBandState requires distinct authored boundary rails")
        _ensure_unique_strings(
            "YRailBandState.dynamic_rail_ids",
            tuple(str(rail_id) for rail_id in self.dynamic_rail_ids),
        )


@dataclass(frozen=True, slots=True)
class ActiveGridState:
    """The currently active logical grid."""

    x_rails: tuple[LogicalXRail, ...]
    y_rails: tuple[LogicalYRail, ...]
    y_bands: tuple[YRailBandState, ...]

    def __post_init__(self) -> None:
        x_ids = tuple(str(rail.rail_id) for rail in self.x_rails)
        x_orders = tuple(str(rail.order) for rail in self.x_rails)
        y_ids = tuple(str(rail.rail_id) for rail in self.y_rails)
        y_ranks = tuple(str(rail.logical_rank) for rail in self.y_rails)
        band_ids = tuple(str(band.band_id) for band in self.y_bands)

        _ensure_unique_strings("ActiveGridState.x_rails ids", x_ids)
        _ensure_unique_strings("ActiveGridState.x_rails orders", x_orders)
        _ensure_unique_strings("ActiveGridState.y_rails ids", y_ids)
        _ensure_unique_strings("ActiveGridState.y_rails logical ranks", y_ranks)
        _ensure_unique_strings("ActiveGridState.y_bands ids", band_ids)

        authored_ids = {
            str(rail.rail_id)
            for rail in self.y_rails
            if rail.kind == "authored"
        }
        dynamic_ids = {
            str(rail.rail_id)
            for rail in self.y_rails
            if rail.kind == "dynamic"
        }
        band_lookup = {str(band.band_id): band for band in self.y_bands}

        for band in self.y_bands:
            if str(band.upper_authored_rail_id) not in authored_ids:
                raise ValueError("Band upper_authored_rail_id must reference an authored y rail")
            if str(band.lower_authored_rail_id) not in authored_ids:
                raise ValueError("Band lower_authored_rail_id must reference an authored y rail")
            for dynamic_rail_id in band.dynamic_rail_ids:
                if str(dynamic_rail_id) not in dynamic_ids:
                    raise ValueError("Band dynamic_rail_ids must reference dynamic y rails in the grid")

        for rail in self.y_rails:
            if rail.kind == "dynamic":
                if rail.band_id is None:
                    raise ValueError("Dynamic y rail must declare band_id")
                if str(rail.band_id) not in band_lookup:
                    raise ValueError("Dynamic y rail band_id must reference an active band")
                if str(rail.rail_id) not in {
                    str(dynamic_rail_id)
                    for dynamic_rail_id in band_lookup[str(rail.band_id)].dynamic_rail_ids
                }:
                    raise ValueError("Dynamic y rail must be listed in its band's dynamic_rail_ids")
