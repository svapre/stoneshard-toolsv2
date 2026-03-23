"""Conservative pre-routing screening over explicit junction-set domains.

Implemented screening subset only:

- active-grid candidate-site checks
- routing-policy schema validation for queried port orientations
- node occupancy from singleton occupied node junctions only
- raw port-capacity contradiction for the narrow supported requirement shape
- adjacent required port-site existence checks

This module intentionally does not implement:

- exact routing
- reachability search
- path construction
- route commitment
- use of non-node junction connection state
- use of already present roads

Section 5 of ``solver_rules.md`` controls actual removals. Broader
reachability-based screening remains open and is not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from toolsv2.routing_policy import is_move_direction_allowed
from toolsv2.solver_types import (
    ActiveGridState,
    CardinalDirection,
    Junction,
    LogicalXRailId,
    LogicalYRailId,
    NodeDefinition,
    NodeDomain,
    NodeId,
    PortDefinition,
    PortId,
    RoutingPolicy,
)


@dataclass(frozen=True, slots=True)
class PortAttachmentRequirement:
    """A narrow screening-time attachment requirement for one named port.

    Current supported subset:

    - one required attachment on a port
    - zero required attachments on a port

    Counts above one remain open unless contradicted immediately by
    port-capacity data.
    """

    port_id: PortId
    required_attachments: int = 1

    def __post_init__(self) -> None:
        if self.required_attachments < 0:
            raise ValueError("required_attachments must be non-negative")


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """Result of local candidate screening."""

    domain: NodeDomain
    has_contradiction: bool


@dataclass(frozen=True, slots=True)
class _PreparedRequirement:
    port: PortDefinition
    required_attachments: int


def _ordered_x_rail_ids(active_grid: ActiveGridState) -> tuple[LogicalXRailId, ...]:
    return tuple(
        rail.rail_id
        for rail in sorted(active_grid.x_rails, key=lambda rail: rail.order)
    )


def _ordered_y_rail_ids(active_grid: ActiveGridState) -> tuple[LogicalYRailId, ...]:
    return tuple(
        rail.rail_id
        for rail in sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    )


def _port_lookup(node_definition: NodeDefinition) -> dict[str, PortDefinition]:
    return {str(port.port_id): port for port in node_definition.ports}


def _prepare_requirements(
    node_definition: NodeDefinition,
    requirements: Sequence[PortAttachmentRequirement],
) -> tuple[tuple[_PreparedRequirement, ...], bool]:
    """Validate the narrow supported requirement shape.

    Returns:
    - prepared requirements
    - whether a raw port-capacity contradiction was proven immediately
    """

    port_lookup = _port_lookup(node_definition)
    required_by_port_id: dict[str, int] = {}
    for requirement in requirements:
        port_id = str(requirement.port_id)
        if port_id not in port_lookup:
            raise ValueError(f"Unknown port_id {requirement.port_id!r} for node {node_definition.node_id!r}")
        required_by_port_id[port_id] = required_by_port_id.get(port_id, 0) + requirement.required_attachments

    if not required_by_port_id:
        return (), False

    orientation_totals: dict[CardinalDirection, int] = {}
    prepared: list[_PreparedRequirement] = []
    for port_id, required_count in required_by_port_id.items():
        port = port_lookup[port_id]

        if required_count > port.capacity:
            return (), True

        if required_count not in {0, 1}:
            raise NotImplementedError(
                "Screening currently supports only 0 or 1 required attachments per port"
            )

        if required_count == 0:
            continue

        orientation_totals[port.orientation] = orientation_totals.get(port.orientation, 0) + required_count
        if orientation_totals[port.orientation] > 1:
            raise NotImplementedError(
                "Screening does not yet support multiple required attachments on the same orientation"
            )

        prepared.append(_PreparedRequirement(port=port, required_attachments=required_count))

    return tuple(prepared), False


def _validate_supported_policy_query(
    routing_policy: RoutingPolicy,
    orientation: CardinalDirection,
) -> None:
    """Validate the narrow supported policy schema for one orientation.

    The current frozen screening subset does not remove candidates from
    broader policy-derived reachability logic. It only requires that the
    routing policy expose the queried movement direction in the narrow schema
    already supported by ``routing_policy.py``.
    """

    is_move_direction_allowed(routing_policy, orientation)


def candidate_port_adjacent_site(
    active_grid: ActiveGridState,
    candidate_junction: Junction,
    orientation: CardinalDirection,
) -> Junction | None:
    """Return the adjacent junction for one candidate/port orientation.

    Returns ``None`` when the required adjacent site does not exist on the
    active grid.
    """

    ordered_x = _ordered_x_rail_ids(active_grid)
    ordered_y = _ordered_y_rail_ids(active_grid)
    x_index_lookup = {rail_id: index for index, rail_id in enumerate(ordered_x)}
    y_index_lookup = {rail_id: index for index, rail_id in enumerate(ordered_y)}

    source_x = x_index_lookup.get(candidate_junction.x_rail_id)
    source_y = y_index_lookup.get(candidate_junction.y_rail_id)
    if source_x is None or source_y is None:
        raise ValueError("Candidate junction must belong to the active grid")

    if orientation == "east":
        target_x = source_x + 1
        target_y = source_y
    elif orientation == "west":
        target_x = source_x - 1
        target_y = source_y
    elif orientation == "south":
        target_x = source_x
        target_y = source_y + 1
    else:
        target_x = source_x
        target_y = source_y - 1

    if target_x < 0 or target_x >= len(ordered_x):
        return None
    if target_y < 0 or target_y >= len(ordered_y):
        return None

    return Junction(
        x_rail_id=ordered_x[target_x],
        y_rail_id=ordered_y[target_y],
    )


def candidate_required_site_is_usable(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    candidate_junction: Junction,
    port: PortDefinition,
    occupied_junctions: frozenset[Junction],
) -> bool:
    """Return whether a required local attachment site is provably usable.

    Current removals stay within the frozen local contradiction subset only:

    - the required adjacent site exists on the active grid
    - the required adjacent site is not already occupied by a singleton node

    The routing policy is consulted only to validate that the narrow supported
    movement-policy schema exists for the port orientation. Stronger
    policy-derived reachability or path-feasibility screening is still open.
    """

    _validate_supported_policy_query(routing_policy, port.orientation)

    adjacent_site = candidate_port_adjacent_site(
        active_grid,
        candidate_junction,
        port.orientation,
    )
    if adjacent_site is None:
        return False
    if adjacent_site in occupied_junctions:
        return False
    return True


def _singleton_occupied_junctions(
    node_domains: Mapping[NodeId, NodeDomain],
    target_node_id: NodeId,
) -> frozenset[Junction]:
    return frozenset(
        next(iter(domain.junctions))
        for node_id, domain in node_domains.items()
        if node_id != target_node_id and len(domain.junctions) == 1
    )


def candidate_survives_screening(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    node_definition: NodeDefinition,
    candidate_junction: Junction,
    target_node_id: NodeId,
    node_domains: Mapping[NodeId, NodeDomain],
    requirements: Sequence[PortAttachmentRequirement] = (),
) -> bool:
    """Return whether one candidate survives the local screening subset."""

    prepared_requirements, raw_capacity_contradiction = _prepare_requirements(
        node_definition,
        requirements,
    )
    if raw_capacity_contradiction:
        return False

    occupied_junctions = _singleton_occupied_junctions(node_domains, target_node_id)
    if candidate_junction in occupied_junctions:
        return False

    for prepared_requirement in prepared_requirements:
        if not candidate_required_site_is_usable(
            active_grid,
            routing_policy,
            candidate_junction,
            prepared_requirement.port,
            occupied_junctions,
        ):
            return False

    return True


def screen_node_domain(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    node_definition: NodeDefinition,
    domain: NodeDomain,
    node_domains: Mapping[NodeId, NodeDomain],
    requirements: Sequence[PortAttachmentRequirement] = (),
    non_node_connection_state: Mapping[Junction, object] | None = None,
) -> ScreeningResult:
    """Filter one node domain by frozen screening contradictions only.

    ``non_node_connection_state`` is accepted for explicit compatibility with
    the solver spec and is ignored by design.
    """

    del non_node_connection_state

    surviving_junctions = frozenset(
        candidate_junction
        for candidate_junction in domain.junctions
        if candidate_survives_screening(
            active_grid=active_grid,
            routing_policy=routing_policy,
            node_definition=node_definition,
            candidate_junction=candidate_junction,
            target_node_id=domain.node_id,
            node_domains=node_domains,
            requirements=requirements,
        )
    )

    screened_domain = NodeDomain(
        node_id=domain.node_id,
        junctions=surviving_junctions,
    )
    return ScreeningResult(
        domain=screened_domain,
        has_contradiction=not screened_domain.junctions,
    )
