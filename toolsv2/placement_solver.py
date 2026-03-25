"""Pass-1 placement-seed search on the current active grid only.

This module implements a conservative placement loop over:

- initial domain construction
- structural propagation
- frozen local screening
- deterministic backtracking search for provisional placement seeds

This module intentionally does not implement:

- exact routing
- refinement
- automatic grid expansion

The returned seeds are pre-routing only. They are not legal graphs, not
canonical, and still require exact routing.

Important distinction:

- any ``max_seeds`` value in this module is a local pass-1 seed-generation cap
- it is not the full-solver final-output ``K``
- full-solver ``K`` applies only after exact routing, refinement, and
  final-output deduplication
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from toolsv2.domain_builder import (
    NodePlacementMetadata,
    OrderedSameRowGroup,
    build_raw_domains,
)
from toolsv2.placement_policy_contracts import PlacementCandidateRanker
from toolsv2.propagation import propagate_domains
from toolsv2.screening import PortAttachmentRequirement, screen_node_domain
from toolsv2.solver_types import (
    ActiveGridState,
    Junction,
    NodeDefinition,
    NodeDomain,
    NodeId,
    RoutingPolicy,
)


PlacementStatus = Literal["success", "failure_on_current_grid"]


@dataclass(frozen=True, slots=True)
class BranchAttempt:
    """One deterministic branch attempt in depth-first search order."""

    node_id: NodeId
    candidate_junction: Junction


@dataclass(frozen=True, slots=True)
class PlacementSeed:
    """One provisional pass-1 placement seed.

    A seed is complete for placement only. It is not a legal graph yet and
    still requires exact routing.
    """

    domains: dict[NodeId, NodeDomain]
    assignments: dict[NodeId, Junction]
    is_legal_graph: Literal[False] = False
    is_canonical: Literal[False] = False
    requires_exact_routing: Literal[True] = True


@dataclass(frozen=True, slots=True)
class PlacementResult:
    """Pass-1 result on the current active grid only.

    The number of returned seeds is a pass-1 search result only. It must not
    be interpreted as the final-output ``K`` of the full solver.
    """

    status: PlacementStatus
    seeds: tuple[PlacementSeed, ...] = ()
    branch_attempts: tuple[BranchAttempt, ...] = ()
    contradiction_observed: bool = False
    failure_domains: dict[NodeId, NodeDomain] | None = None


@dataclass(frozen=True, slots=True)
class _StabilizationResult:
    domains: dict[NodeId, NodeDomain]
    has_contradiction: bool


@dataclass(frozen=True, slots=True)
class _SearchOutcome:
    seeds: tuple[PlacementSeed, ...]
    branch_attempts: tuple[BranchAttempt, ...]
    contradiction_observed: bool
    failure_domains: dict[NodeId, NodeDomain] | None = None


def _validate_node_definitions(
    node_definitions: Mapping[NodeId, NodeDefinition],
    node_metadata: Sequence[NodePlacementMetadata],
) -> None:
    for metadata in node_metadata:
        if metadata.node_id not in node_definitions:
            raise ValueError(f"Missing NodeDefinition for node {metadata.node_id!r}")


def _validate_requirement_keys(
    node_definitions: Mapping[NodeId, NodeDefinition],
    port_requirements_by_node_id: Mapping[NodeId, Sequence[PortAttachmentRequirement]],
) -> None:
    for node_id in port_requirements_by_node_id:
        if node_id not in node_definitions:
            raise ValueError(f"Unknown node id {node_id!r} in port requirements")


def _x_order_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    return {str(rail.rail_id): rail.order for rail in active_grid.x_rails}


def _y_index_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    ordered_y_rails = sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    return {
        str(rail.rail_id): index
        for index, rail in enumerate(ordered_y_rails)
    }


def _sorted_junctions(
    active_grid: ActiveGridState,
    junctions: frozenset[Junction],
) -> tuple[Junction, ...]:
    """Return a deterministic candidate order for search only.

    This ordering is a search-order tie-breaker. It is not a solver objective
    and it must not be treated as a preference among legal solutions.
    """

    x_order = _x_order_lookup(active_grid)
    y_index = _y_index_lookup(active_grid)
    return tuple(
        sorted(
            junctions,
            key=lambda junction: (
                x_order[str(junction.x_rail_id)],
                y_index[str(junction.y_rail_id)],
            ),
        )
    )


def _ordered_candidate_junctions(
    active_grid: ActiveGridState,
    branch_node_id: NodeId,
    junctions: frozenset[Junction],
    domains: Mapping[NodeId, NodeDomain],
    minimum_same_row_gap: int,
    candidate_ranker: PlacementCandidateRanker | None,
) -> tuple[Junction, ...]:
    default_order = _sorted_junctions(active_grid, junctions)
    if candidate_ranker is None:
        return default_order

    ranked = candidate_ranker(
        active_grid,
        branch_node_id,
        junctions,
        domains,
        minimum_same_row_gap,
    )
    if set(ranked) != set(junctions):
        raise ValueError("candidate_ranker must return exactly the supplied candidate junctions")
    if len(ranked) != len(junctions):
        raise ValueError("candidate_ranker must not repeat candidate junctions")
    return ranked


def _all_domains_singleton(domains: Mapping[NodeId, NodeDomain]) -> bool:
    return all(len(domain.junctions) == 1 for domain in domains.values())


def _singleton_assignments(domains: Mapping[NodeId, NodeDomain]) -> dict[NodeId, Junction]:
    return {
        node_id: next(iter(domain.junctions))
        for node_id, domain in domains.items()
        if len(domain.junctions) == 1
    }


def _build_seed(domains: Mapping[NodeId, NodeDomain]) -> PlacementSeed:
    copied_domains = {
        node_id: NodeDomain(
            node_id=domain.node_id,
            junctions=frozenset(domain.junctions),
        )
        for node_id, domain in domains.items()
    }
    return PlacementSeed(
        domains=copied_domains,
        assignments=_singleton_assignments(copied_domains),
    )


def _choose_branch_node_id(domains: Mapping[NodeId, NodeDomain]) -> NodeId | None:
    unresolved = [
        node_id
        for node_id, domain in domains.items()
        if len(domain.junctions) > 1
    ]
    if not unresolved:
        return None

    return min(
        unresolved,
        key=lambda node_id: (len(domains[node_id].junctions), str(node_id)),
    )


def _screen_all_domains(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    domains: dict[NodeId, NodeDomain],
    node_definitions: Mapping[NodeId, NodeDefinition],
    port_requirements_by_node_id: Mapping[NodeId, Sequence[PortAttachmentRequirement]],
) -> dict[NodeId, NodeDomain]:
    screened_domains: dict[NodeId, NodeDomain] = {}
    for node_id, domain in domains.items():
        node_definition = node_definitions.get(node_id)
        if node_definition is None:
            raise ValueError(f"Missing NodeDefinition for node {node_id!r}")

        screening_result = screen_node_domain(
            active_grid=active_grid,
            routing_policy=routing_policy,
            node_definition=node_definition,
            domain=domain,
            node_domains=domains,
            requirements=tuple(port_requirements_by_node_id.get(node_id, ())),
        )
        screened_domains[node_id] = screening_result.domain

    return screened_domains


def _has_empty_domain(domains: Mapping[NodeId, NodeDomain]) -> bool:
    return any(not domain.junctions for domain in domains.values())


def _stabilize_domains(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    domains: dict[NodeId, NodeDomain],
    node_definitions: Mapping[NodeId, NodeDefinition],
    node_metadata: Sequence[NodePlacementMetadata],
    ordered_same_row_groups: Sequence[OrderedSameRowGroup],
    port_requirements_by_node_id: Mapping[NodeId, Sequence[PortAttachmentRequirement]],
    minimum_same_row_gap: int,
) -> _StabilizationResult:
    current_domains = dict(domains)

    while True:
        propagation_result = propagate_domains(
            active_grid=active_grid,
            domains=current_domains,
            node_metadata=node_metadata,
            ordered_same_row_groups=ordered_same_row_groups,
            minimum_same_row_gap=minimum_same_row_gap,
        )
        if propagation_result.has_contradiction:
            return _StabilizationResult(
                domains=propagation_result.domains,
                has_contradiction=True,
            )

        screened_domains = _screen_all_domains(
            active_grid=active_grid,
            routing_policy=routing_policy,
            domains=propagation_result.domains,
            node_definitions=node_definitions,
            port_requirements_by_node_id=port_requirements_by_node_id,
        )
        if _has_empty_domain(screened_domains):
            return _StabilizationResult(
                domains=screened_domains,
                has_contradiction=True,
            )

        if screened_domains == current_domains:
            return _StabilizationResult(
                domains=screened_domains,
                has_contradiction=False,
            )

        current_domains = screened_domains


def _search_current_grid(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    node_definitions: Mapping[NodeId, NodeDefinition],
    node_metadata: Sequence[NodePlacementMetadata],
    ordered_same_row_groups: Sequence[OrderedSameRowGroup],
    port_requirements_by_node_id: Mapping[NodeId, Sequence[PortAttachmentRequirement]],
    minimum_same_row_gap: int,
    candidate_ranker: PlacementCandidateRanker | None,
    domains: dict[NodeId, NodeDomain],
    branch_attempts: tuple[BranchAttempt, ...],
    remaining_seed_limit: int,
) -> _SearchOutcome:
    stabilized = _stabilize_domains(
        active_grid=active_grid,
        routing_policy=routing_policy,
        domains=domains,
        node_definitions=node_definitions,
        node_metadata=node_metadata,
        ordered_same_row_groups=ordered_same_row_groups,
        port_requirements_by_node_id=port_requirements_by_node_id,
        minimum_same_row_gap=minimum_same_row_gap,
    )
    if stabilized.has_contradiction:
        return _SearchOutcome(
            seeds=(),
            branch_attempts=branch_attempts,
            contradiction_observed=True,
            failure_domains=stabilized.domains,
        )

    if _all_domains_singleton(stabilized.domains):
        return _SearchOutcome(
            seeds=(_build_seed(stabilized.domains),),
            branch_attempts=branch_attempts,
            contradiction_observed=False,
        )

    branch_node_id = _choose_branch_node_id(stabilized.domains)
    if branch_node_id is None:
        return _SearchOutcome(
            seeds=(),
            branch_attempts=branch_attempts,
            contradiction_observed=False,
            failure_domains=stabilized.domains,
        )

    explored_attempts = branch_attempts
    contradiction_observed = False
    found_seeds: list[PlacementSeed] = []
    failure_domains: dict[NodeId, NodeDomain] | None = None
    for candidate_junction in _ordered_candidate_junctions(
        active_grid=active_grid,
        branch_node_id=branch_node_id,
        junctions=stabilized.domains[branch_node_id].junctions,
        domains=stabilized.domains,
        minimum_same_row_gap=minimum_same_row_gap,
        candidate_ranker=candidate_ranker,
    ):
        if len(found_seeds) >= remaining_seed_limit:
            break

        next_attempts = explored_attempts + (
            BranchAttempt(
                node_id=branch_node_id,
                candidate_junction=candidate_junction,
            ),
        )
        branch_domains = dict(stabilized.domains)
        branch_domains[branch_node_id] = NodeDomain(
            node_id=branch_node_id,
            junctions=frozenset({candidate_junction}),
        )

        branch_result = _search_current_grid(
            active_grid=active_grid,
            routing_policy=routing_policy,
            node_definitions=node_definitions,
            node_metadata=node_metadata,
            ordered_same_row_groups=ordered_same_row_groups,
            port_requirements_by_node_id=port_requirements_by_node_id,
            minimum_same_row_gap=minimum_same_row_gap,
            candidate_ranker=candidate_ranker,
            domains=branch_domains,
            branch_attempts=next_attempts,
            remaining_seed_limit=remaining_seed_limit - len(found_seeds),
        )
        found_seeds.extend(branch_result.seeds)
        explored_attempts = branch_result.branch_attempts
        contradiction_observed = contradiction_observed or branch_result.contradiction_observed
        if branch_result.failure_domains is not None:
            failure_domains = branch_result.failure_domains

    if found_seeds:
        return _SearchOutcome(
            seeds=tuple(found_seeds),
            branch_attempts=explored_attempts,
            contradiction_observed=contradiction_observed,
        )

    return _SearchOutcome(
        seeds=(),
        branch_attempts=explored_attempts,
        contradiction_observed=contradiction_observed,
        failure_domains=failure_domains or stabilized.domains,
    )


def solve_placement_on_current_grid(
    active_grid: ActiveGridState,
    routing_policy: RoutingPolicy,
    node_definitions: Mapping[NodeId, NodeDefinition],
    node_metadata: Sequence[NodePlacementMetadata],
    ordered_same_row_groups: Sequence[OrderedSameRowGroup] = (),
    port_requirements_by_node_id: Mapping[NodeId, Sequence[PortAttachmentRequirement]] | None = None,
    max_seeds: int = 1,
    minimum_same_row_gap: int = 1,
    candidate_junction_ranker: PlacementCandidateRanker | None = None,
) -> PlacementResult:
    """Return up to ``max_seeds`` provisional placement seeds on the current grid.

    The search uses only frozen pass-1 operations:

    - initial domain construction
    - propagation
    - screening
    - deterministic branching and backtracking

    ``max_seeds`` is a local pass-1 seed-generation cap only. It is not the
    final-output ``K`` of the full solver.
    """

    if max_seeds < 1:
        raise ValueError("max_seeds must be at least 1")
    if minimum_same_row_gap < 0:
        raise ValueError("minimum_same_row_gap must be non-negative")

    normalized_requirements = port_requirements_by_node_id or {}
    _validate_node_definitions(node_definitions, node_metadata)
    _validate_requirement_keys(node_definitions, normalized_requirements)

    initial_domains = build_raw_domains(
        active_grid=active_grid,
        node_metadata=node_metadata,
        ordered_same_row_groups=ordered_same_row_groups,
        minimum_same_row_gap=minimum_same_row_gap,
    )
    search_outcome = _search_current_grid(
        active_grid=active_grid,
        routing_policy=routing_policy,
        node_definitions=node_definitions,
        node_metadata=node_metadata,
        ordered_same_row_groups=ordered_same_row_groups,
        port_requirements_by_node_id=normalized_requirements,
        minimum_same_row_gap=minimum_same_row_gap,
        candidate_ranker=candidate_junction_ranker,
        domains=initial_domains,
        branch_attempts=(),
        remaining_seed_limit=max_seeds,
    )
    if search_outcome.seeds:
        return PlacementResult(
            status="success",
            seeds=search_outcome.seeds,
            branch_attempts=search_outcome.branch_attempts,
            contradiction_observed=search_outcome.contradiction_observed,
        )

    return PlacementResult(
        status="failure_on_current_grid",
        seeds=(),
        branch_attempts=search_outcome.branch_attempts,
        contradiction_observed=search_outcome.contradiction_observed,
        failure_domains=search_outcome.failure_domains,
    )
