from __future__ import annotations

import ast
import inspect
import unittest
from unittest.mock import patch

import toolsv2.placement_solver as placement_solver_module
from toolsv2.domain_builder import NodePlacementMetadata
from toolsv2.placement_solver import solve_placement_on_current_grid
from toolsv2.profile import build_minimum_active_grid
from toolsv2.screening import PortAttachmentRequirement
from toolsv2.solver_types import (
    Junction,
    LogicalYRailId,
    NodeDefinition,
    NodeDomain,
    NodeId,
    PortDefinition,
    PortId,
    RoutingPolicy,
)


def _grid(*x_ids: str) -> object:
    return build_minimum_active_grid(
        default_x_rail_ids=x_ids,
        authored_tier_rail_ids=("tier_0",),
    )


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="placement_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


def _node_definition(node_id: str) -> NodeDefinition:
    return NodeDefinition(
        node_id=NodeId(node_id),
        kind="generic",
        ports=(),
    )


def _node_definition_with_port(
    node_id: str,
    port_id: str,
    orientation: str,
) -> NodeDefinition:
    return NodeDefinition(
        node_id=NodeId(node_id),
        kind="generic",
        ports=(
            PortDefinition(
                port_id=PortId(port_id),
                orientation=orientation,  # type: ignore[arg-type]
                capacity=1,
            ),
        ),
    )


def _metadata(*node_ids: str) -> tuple[NodePlacementMetadata, ...]:
    return tuple(
        NodePlacementMetadata(
            node_id=NodeId(node_id),
            authored_tier_y_rail_id=LogicalYRailId("tier_0"),
        )
        for node_id in node_ids
    )


def _domain(node_id: str, *junctions: Junction) -> NodeDomain:
    return NodeDomain(
        node_id=NodeId(node_id),
        junctions=frozenset(junctions),
    )


class PlacementSolverTests(unittest.TestCase):
    def test_default_seed_generation_limit_is_one_when_multiple_seeds_exist(self) -> None:
        grid = _grid("x0", "x1", "x2")
        raw_domains = {
            NodeId("a"): _domain(
                "a",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
            )

        self.assertEqual("success", result.status)
        self.assertEqual(1, len(result.seeds))
        self.assertEqual(
            Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
            result.seeds[0].assignments[NodeId("a")],
        )

    def test_first_branch_candidate_can_succeed_when_adjacent_occupied_site_is_not_a_proof(self) -> None:
        grid = _grid("x0", "x1", "x2")
        a_left = Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id)
        a_right = Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id)
        b_fixed = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        raw_domains = {
            NodeId("a"): _domain("a", a_left, a_right),
            NodeId("b"): _domain("b", b_fixed),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition_with_port("b", "east_out", "east"),
                },
                node_metadata=_metadata("a", "b"),
                port_requirements_by_node_id={
                    NodeId("b"): (PortAttachmentRequirement(port_id=PortId("east_out")),),
                },
            )

        self.assertEqual("success", result.status)
        self.assertEqual(1, len(result.seeds))
        self.assertEqual(
            (Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),),
            tuple(attempt.candidate_junction for attempt in result.branch_attempts),
        )
        self.assertEqual(NodeId("a"), result.branch_attempts[0].node_id)
        self.assertEqual(a_left, result.seeds[0].assignments[NodeId("a")])
        self.assertEqual(b_fixed, result.seeds[0].assignments[NodeId("b")])

    def test_candidate_junction_ranker_can_override_default_left_to_right_branch_order(self) -> None:
        grid = _grid("x0", "x1", "x2")
        left = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        right = Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id)
        raw_domains = {
            NodeId("a"): _domain("a", left, right),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        def _reverse_ranker(active_grid, branch_node_id, candidate_junctions, domains, minimum_same_row_gap):
            self.assertEqual(NodeId("a"), branch_node_id)
            return tuple(reversed(sorted(candidate_junctions, key=lambda junction: str(junction.x_rail_id))))

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
                candidate_junction_ranker=_reverse_ranker,
            )

        self.assertEqual("success", result.status)
        self.assertEqual(right, result.seeds[0].assignments[NodeId("a")])

    def test_adjacent_occupied_sites_do_not_force_current_grid_contradiction(self) -> None:
        grid = _grid("x0", "x1", "x2", "x3")
        a_left = Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id)
        a_right = Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id)
        b_fixed = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        c_fixed = Junction(grid.x_rails[3].rail_id, grid.y_rails[0].rail_id)
        raw_domains = {
            NodeId("a"): _domain("a", a_left, a_right),
            NodeId("b"): _domain("b", b_fixed),
            NodeId("c"): _domain("c", c_fixed),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition_with_port("b", "east_out", "east"),
                    NodeId("c"): _node_definition_with_port("c", "west_out", "west"),
                },
                node_metadata=_metadata("a", "b", "c"),
                port_requirements_by_node_id={
                    NodeId("b"): (PortAttachmentRequirement(port_id=PortId("east_out")),),
                    NodeId("c"): (PortAttachmentRequirement(port_id=PortId("west_out")),),
                },
            )

        self.assertEqual("success", result.status)
        self.assertEqual(1, len(result.seeds))
        self.assertEqual(NodeId("a"), result.branch_attempts[0].node_id)
        self.assertEqual(a_left, result.seeds[0].assignments[NodeId("a")])
        self.assertEqual(b_fixed, result.seeds[0].assignments[NodeId("b")])
        self.assertEqual(c_fixed, result.seeds[0].assignments[NodeId("c")])

    def test_smallest_domain_first_branching(self) -> None:
        grid = _grid("x0", "x1", "x2", "x3", "x4", "x5")
        raw_domains = {
            NodeId("a"): _domain(
                "a",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[3].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[4].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("c"): _domain(
                "c",
                Junction(grid.x_rails[5].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                    NodeId("c"): _node_definition("c"),
                },
                node_metadata=_metadata("a", "b", "c"),
            )

        self.assertEqual("success", result.status)
        self.assertEqual(1, len(result.seeds))
        self.assertEqual(NodeId("a"), result.branch_attempts[0].node_id)

    def test_deterministic_fallback_when_domain_sizes_tie(self) -> None:
        grid = _grid("x0", "x1", "x2", "x3", "x4")
        raw_domains = {
            NodeId("a_node"): _domain(
                "a_node",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b_node"): _domain(
                "b_node",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[3].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("c_node"): _domain(
                "c_node",
                Junction(grid.x_rails[4].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a_node"): _node_definition("a_node"),
                    NodeId("b_node"): _node_definition("b_node"),
                    NodeId("c_node"): _node_definition("c_node"),
                },
                node_metadata=_metadata("a_node", "b_node", "c_node"),
            )

        self.assertEqual("success", result.status)
        self.assertEqual(1, len(result.seeds))
        self.assertEqual(NodeId("a_node"), result.branch_attempts[0].node_id)

    def test_caller_override_seed_generation_limit_returns_multiple_provisional_seeds(self) -> None:
        grid = _grid("x0", "x1", "x2")
        raw_domains = {
            NodeId("a"): _domain(
                "a",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
                max_seeds=2,
            )

        self.assertEqual("success", result.status)
        self.assertEqual(2, len(result.seeds))
        self.assertEqual(
            (
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            tuple(seed.assignments[NodeId("a")] for seed in result.seeds),
        )

    def test_each_returned_seed_is_complete_placement_only(self) -> None:
        grid = _grid("x0", "x1", "x2")
        raw_domains = {
            NodeId("a"): _domain(
                "a",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            result = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
                max_seeds=2,
            )

        self.assertEqual("success", result.status)
        for seed in result.seeds:
            self.assertEqual({NodeId("a"), NodeId("b")}, set(seed.assignments))
            self.assertEqual(1, len(seed.domains[NodeId("a")].junctions))
            self.assertEqual(1, len(seed.domains[NodeId("b")].junctions))
            self.assertFalse(seed.is_legal_graph)
            self.assertFalse(seed.is_canonical)
            self.assertTrue(seed.requires_exact_routing)

    def test_deterministic_traversal_produces_reproducible_seed_order(self) -> None:
        grid = _grid("x0", "x1", "x2")
        raw_domains = {
            NodeId("a"): _domain(
                "a",
                Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
            ),
            NodeId("b"): _domain(
                "b",
                Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id),
            ),
        }

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            first = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
                max_seeds=2,
            )

        with patch("toolsv2.placement_solver.build_raw_domains", return_value=raw_domains):
            second = solve_placement_on_current_grid(
                active_grid=grid,
                routing_policy=_policy(),
                node_definitions={
                    NodeId("a"): _node_definition("a"),
                    NodeId("b"): _node_definition("b"),
                },
                node_metadata=_metadata("a", "b"),
                max_seeds=2,
            )

        self.assertEqual(
            tuple(seed.assignments[NodeId("a")] for seed in first.seeds),
            tuple(seed.assignments[NodeId("a")] for seed in second.seeds),
        )

    def test_no_routing_or_refinement_module_is_imported(self) -> None:
        tree = ast.parse(inspect.getsource(placement_solver_module))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

        self.assertFalse(any(module.endswith(".router") for module in imported_modules))
        self.assertFalse(any(module.endswith(".refinement") for module in imported_modules))


if __name__ == "__main__":
    unittest.main()
