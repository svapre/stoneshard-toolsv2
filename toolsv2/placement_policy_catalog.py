"""External graph-content placement policy registry.

This module keeps graph/content-specific candidate-ranking behavior out of the
generic placement solver. Policies here may inspect the explicit route graph
and current partial placement state, but they only rank already-legal
candidate junctions; they do not change placement legality.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping

from toolsv2.domain_builder import enumerate_minimum_gap_ordered_row_assignments
from toolsv2.graph_content import GraphContentModel
from toolsv2.placement_policy_contracts import PlacementCandidateRanker
from toolsv2.solver_common import ActiveGridState, Junction, NodeId
from toolsv2.solver_types import NodeDomain


V1_SKILL_TREE_ROUTE_GRAPH_SPRING_POLICY_ID = "skill_tree_route_graph_spring"


def _x_order_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    return {str(rail.rail_id): rail.order for rail in active_grid.x_rails}


def _y_index_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    ordered_y_rails = sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    return {
        str(rail.rail_id): index
        for index, rail in enumerate(ordered_y_rails)
    }


def _default_candidate_order(
    active_grid: ActiveGridState,
    candidate_junctions: frozenset[Junction],
) -> tuple[Junction, ...]:
    x_order = _x_order_lookup(active_grid)
    y_index = _y_index_lookup(active_grid)
    return tuple(
        sorted(
            candidate_junctions,
            key=lambda junction: (
                x_order[str(junction.x_rail_id)],
                y_index[str(junction.y_rail_id)],
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class _RouteGraphSpringCandidateRanker:
    neighbor_nodes_by_node_id: Mapping[NodeId, frozenset[NodeId]]
    ordered_same_row_group_by_node_id: Mapping[NodeId, tuple[NodeId, ...]]

    def __call__(
        self,
        active_grid: ActiveGridState,
        branch_node_id: NodeId,
        candidate_junctions: frozenset[Junction],
        domains: Mapping[NodeId, NodeDomain],
        minimum_same_row_gap: int,
    ) -> tuple[Junction, ...]:
        default_order = _default_candidate_order(active_grid, candidate_junctions)
        if not candidate_junctions:
            return default_order

        ideal_x_by_node_id = _solve_harmonic_x_ideals(
            active_grid,
            self.neighbor_nodes_by_node_id,
            domains,
            branch_node_id,
        )
        branch_ideal_x = ideal_x_by_node_id.get(branch_node_id)
        if branch_ideal_x is None:
            return default_order

        x_order = _x_order_lookup(active_grid)
        y_index = _y_index_lookup(active_grid)
        row_group = self.ordered_same_row_group_by_node_id.get(branch_node_id)

        def _candidate_key(junction: Junction) -> tuple[float, float, int, int]:
            row_cost = 0.0
            if row_group is not None:
                row_cost = _best_same_row_group_projection_cost(
                    active_grid=active_grid,
                    domains=domains,
                    ordered_node_ids=row_group,
                    branch_node_id=branch_node_id,
                    branch_candidate_junction=junction,
                    ideal_x_by_node_id=ideal_x_by_node_id,
                    minimum_same_row_gap=minimum_same_row_gap,
                )
            candidate_x = float(x_order[str(junction.x_rail_id)])
            return (
                row_cost,
                abs(candidate_x - branch_ideal_x),
                x_order[str(junction.x_rail_id)],
                y_index[str(junction.y_rail_id)],
            )

        return tuple(sorted(candidate_junctions, key=_candidate_key))


def _singleton_anchor_x_by_node_id(
    active_grid: ActiveGridState,
    domains: Mapping[NodeId, NodeDomain],
) -> dict[NodeId, float]:
    x_order = _x_order_lookup(active_grid)
    anchors: dict[NodeId, float] = {}
    for node_id, domain in domains.items():
        if len(domain.junctions) != 1:
            continue
        junction = next(iter(domain.junctions))
        anchors[node_id] = float(x_order[str(junction.x_rail_id)])
    return anchors


def _connected_component(
    neighbor_nodes_by_node_id: Mapping[NodeId, frozenset[NodeId]],
    start_node_id: NodeId,
) -> frozenset[NodeId]:
    component: set[NodeId] = {start_node_id}
    queue: deque[NodeId] = deque((start_node_id,))
    while queue:
        node_id = queue.popleft()
        for neighbor_node_id in neighbor_nodes_by_node_id.get(node_id, ()):
            if neighbor_node_id in component:
                continue
            component.add(neighbor_node_id)
            queue.append(neighbor_node_id)
    return frozenset(component)


def _solve_harmonic_x_ideals(
    active_grid: ActiveGridState,
    neighbor_nodes_by_node_id: Mapping[NodeId, frozenset[NodeId]],
    domains: Mapping[NodeId, NodeDomain],
    start_node_id: NodeId,
) -> dict[NodeId, float]:
    if start_node_id not in neighbor_nodes_by_node_id:
        return {}

    component = _connected_component(neighbor_nodes_by_node_id, start_node_id)
    anchors = {
        node_id: x_value
        for node_id, x_value in _singleton_anchor_x_by_node_id(active_grid, domains).items()
        if node_id in component
    }
    if not anchors:
        return {}

    unknowns = tuple(
        node_id
        for node_id in sorted(component, key=str)
        if node_id not in anchors
    )
    if not unknowns:
        return anchors

    index_by_node_id = {
        node_id: index
        for index, node_id in enumerate(unknowns)
    }
    size = len(unknowns)
    matrix = [
        [0.0 for _ in range(size)]
        for _ in range(size)
    ]
    rhs = [0.0 for _ in range(size)]

    for node_id in unknowns:
        neighbors = tuple(
            sorted(neighbor_nodes_by_node_id.get(node_id, ()), key=str)
        )
        degree = len(neighbors)
        if degree == 0:
            return {}
        row_index = index_by_node_id[node_id]
        matrix[row_index][row_index] = float(degree)
        for neighbor_node_id in neighbors:
            if neighbor_node_id not in component:
                continue
            if neighbor_node_id in anchors:
                rhs[row_index] += anchors[neighbor_node_id]
                continue
            matrix[row_index][index_by_node_id[neighbor_node_id]] -= 1.0

    solved = _solve_linear_system(matrix, rhs)
    if solved is None:
        return {}

    return anchors | {
        node_id: solved[index_by_node_id[node_id]]
        for node_id in unknowns
    }


def _solve_linear_system(
    matrix: list[list[float]],
    rhs: list[float],
) -> list[float] | None:
    size = len(rhs)
    for column_index in range(size):
        pivot_index = max(
            range(column_index, size),
            key=lambda row_index: abs(matrix[row_index][column_index]),
        )
        if abs(matrix[pivot_index][column_index]) < 1e-9:
            return None
        if pivot_index != column_index:
            matrix[column_index], matrix[pivot_index] = matrix[pivot_index], matrix[column_index]
            rhs[column_index], rhs[pivot_index] = rhs[pivot_index], rhs[column_index]

        pivot = matrix[column_index][column_index]
        matrix[column_index] = [
            value / pivot
            for value in matrix[column_index]
        ]
        rhs[column_index] /= pivot

        for row_index in range(size):
            if row_index == column_index:
                continue
            factor = matrix[row_index][column_index]
            if abs(factor) < 1e-9:
                continue
            matrix[row_index] = [
                row_value - factor * pivot_value
                for row_value, pivot_value in zip(matrix[row_index], matrix[column_index])
            ]
            rhs[row_index] -= factor * rhs[column_index]

    return rhs


def _node_domain_x_rail_ids(domain: NodeDomain) -> frozenset[str]:
    return frozenset(str(junction.x_rail_id) for junction in domain.junctions)


def _best_same_row_group_projection_cost(
    *,
    active_grid: ActiveGridState,
    domains: Mapping[NodeId, NodeDomain],
    ordered_node_ids: tuple[NodeId, ...],
    branch_node_id: NodeId,
    branch_candidate_junction: Junction,
    ideal_x_by_node_id: Mapping[NodeId, float],
    minimum_same_row_gap: int,
) -> float:
    ordered_x_rail_ids = tuple(
        rail.rail_id
        for rail in sorted(active_grid.x_rails, key=lambda rail: rail.order)
    )
    x_order = _x_order_lookup(active_grid)
    candidate_x_rail_id = str(branch_candidate_junction.x_rail_id)
    feasible_assignments = enumerate_minimum_gap_ordered_row_assignments(
        ordered_x_rail_ids,
        len(ordered_node_ids),
        minimum_same_row_gap=minimum_same_row_gap,
    )

    best_cost: float | None = None
    for assignment in feasible_assignments:
        assignment_by_node_id = {
            node_id: str(assignment[index])
            for index, node_id in enumerate(ordered_node_ids)
        }
        if assignment_by_node_id[branch_node_id] != candidate_x_rail_id:
            continue

        feasible = True
        cost = 0.0
        for node_id in ordered_node_ids:
            domain = domains[node_id]
            assigned_x_rail_id = assignment_by_node_id[node_id]
            if assigned_x_rail_id not in _node_domain_x_rail_ids(domain):
                feasible = False
                break
            ideal_x = ideal_x_by_node_id.get(node_id)
            if ideal_x is not None:
                delta = float(x_order[assigned_x_rail_id]) - ideal_x
                cost += delta * delta
        if not feasible:
            continue
        if best_cost is None or cost < best_cost:
            best_cost = cost

    if best_cost is None:
        return float("inf")
    return best_cost


def _build_neighbor_nodes_by_node_id(
    content: GraphContentModel,
) -> dict[NodeId, frozenset[NodeId]]:
    neighbor_nodes: dict[NodeId, set[NodeId]] = defaultdict(set)
    for requirement in content.route_requirements:
        neighbor_nodes[requirement.source_node_id].add(requirement.sink_node_id)
        neighbor_nodes[requirement.sink_node_id].add(requirement.source_node_id)
    return {
        node_id: frozenset(neighbors)
        for node_id, neighbors in neighbor_nodes.items()
    }


def _build_ordered_same_row_group_by_node_id(
    content: GraphContentModel,
) -> dict[NodeId, tuple[NodeId, ...]]:
    grouped: dict[NodeId, tuple[NodeId, ...]] = {}
    for group in content.ordered_same_row_groups:
        ordered_node_ids = tuple(group.ordered_node_ids)
        for node_id in ordered_node_ids:
            grouped[node_id] = ordered_node_ids
    return grouped


def build_v1_skill_tree_route_graph_spring_candidate_ranker(
    content: GraphContentModel,
) -> PlacementCandidateRanker:
    """Build the current skill-tree graph-guided spring ranking policy."""

    return _RouteGraphSpringCandidateRanker(
        neighbor_nodes_by_node_id=_build_neighbor_nodes_by_node_id(content),
        ordered_same_row_group_by_node_id=_build_ordered_same_row_group_by_node_id(content),
    )


def resolve_graph_content_candidate_ranker(
    content: GraphContentModel,
) -> PlacementCandidateRanker | None:
    """Resolve one external content-owned placement candidate ranker."""

    policy_id = content.placement_candidate_policy_id
    if policy_id is None:
        return None
    if policy_id == V1_SKILL_TREE_ROUTE_GRAPH_SPRING_POLICY_ID:
        return build_v1_skill_tree_route_graph_spring_candidate_ranker(content)
    raise ValueError(f"Unknown placement candidate policy id: {policy_id}")

