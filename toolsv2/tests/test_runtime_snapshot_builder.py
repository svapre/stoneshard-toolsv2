from __future__ import annotations

import unittest

from toolsv2.profile import build_minimum_active_grid
from toolsv2.placement_solver import PlacementSeed
from toolsv2.runtime_snapshot_builder import V1RuntimeSnapshotBuilder
from toolsv2.solver_schema import NodeDefinition, PortDefinition
from toolsv2.solver_types import Junction, NodeDomain, NodeId, PortId


class RuntimeSnapshotBuilderTests(unittest.TestCase):
    def _build_seed(self, node_id: NodeId, junction) -> PlacementSeed:
        domain = NodeDomain(
            node_id=node_id,
            junctions=frozenset({junction}),
        )
        return PlacementSeed(
            domains={node_id: domain},
            assignments={node_id: junction},
        )

    def test_builder_returns_valid_initial_port_graph_state_for_minimal_seed(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, _ = tuple(
            sorted(
                self._junctions_from_grid(active_grid),
                key=lambda junction: str(junction.x_rail_id),
            )
        )
        node_id = NodeId("source")
        builder = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(
                        PortDefinition(
                            port_id=PortId("east"),
                            orientation="east",
                            capacity=1,
                        ),
                    ),
                ),
            },
        )

        state = builder(self._build_seed(node_id, left_junction))

        self.assertEqual(1, len(state.objects.nodes))
        self.assertEqual(2, len(state.objects.junctions))
        self.assertEqual((), state.objects.edges)
        self.assertEqual(0, len(state.graph.edge_ids))

    def test_placed_nodes_appear_at_the_correct_occupied_junction(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, _ = tuple(
            sorted(
                self._junctions_from_grid(active_grid),
                key=lambda junction: str(junction.x_rail_id),
            )
        )
        node_id = NodeId("source")
        state = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(),
                ),
            },
        )(self._build_seed(node_id, left_junction))

        self.assertEqual(left_junction, state.objects.nodes[0].current_junction_id)
        occupied_junction = next(
            junction
            for junction in state.objects.junctions
            if junction.junction_id == left_junction
        )
        self.assertEqual(node_id, occupied_junction.occupying_node_id)

    def test_occupied_junctions_become_inactive(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, _ = tuple(
            sorted(
                self._junctions_from_grid(active_grid),
                key=lambda junction: str(junction.x_rail_id),
            )
        )
        node_id = NodeId("source")
        state = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(),
                ),
            },
        )(self._build_seed(node_id, left_junction))

        occupied_junction = next(
            junction
            for junction in state.objects.junctions
            if junction.junction_id == left_junction
        )
        self.assertFalse(occupied_junction.is_active)

    def test_unoccupied_junctions_remain_active(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = tuple(
            sorted(
                self._junctions_from_grid(active_grid),
                key=lambda junction: str(junction.x_rail_id),
            )
        )
        node_id = NodeId("source")
        state = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(),
                ),
            },
        )(self._build_seed(node_id, left_junction))

        unoccupied_junction = next(
            junction
            for junction in state.objects.junctions
            if junction.junction_id == right_junction
        )
        self.assertTrue(unoccupied_junction.is_active)
        self.assertIsNone(unoccupied_junction.occupying_node_id)

    def test_no_built_route_edges_are_created_just_from_placement(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        only_junction = next(iter(self._junctions_from_grid(active_grid)))
        node_id = NodeId("source")
        state = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(
                        PortDefinition(
                            port_id=PortId("east"),
                            orientation="east",
                            capacity=1,
                        ),
                    ),
                ),
            },
        )(self._build_seed(node_id, only_junction))

        self.assertEqual((), state.objects.edges)
        self.assertEqual((), state.graph.edge_ids)

    def test_builder_is_deterministic_for_the_same_seed(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        only_junction = next(iter(self._junctions_from_grid(active_grid)))
        node_id = NodeId("source")
        builder = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(
                        PortDefinition(
                            port_id=PortId("east"),
                            orientation="east",
                            capacity=1,
                        ),
                    ),
                ),
            },
        )
        seed = self._build_seed(node_id, only_junction)

        first_state = builder(seed)
        second_state = builder(seed)

        self.assertEqual(first_state, second_state)

    def test_builder_does_not_mutate_input_placement_seed(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        only_junction = next(iter(self._junctions_from_grid(active_grid)))
        node_id = NodeId("source")
        seed = self._build_seed(node_id, only_junction)
        original_domains = dict(seed.domains)
        original_assignments = dict(seed.assignments)
        builder = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions={
                node_id: NodeDefinition(
                    node_id=node_id,
                    kind="basic",
                    ports=(),
                ),
            },
        )

        _ = builder(seed)

        self.assertEqual(original_domains, seed.domains)
        self.assertEqual(original_assignments, seed.assignments)

    def _junctions_from_grid(self, active_grid):
        ordered_x = sorted(active_grid.x_rails, key=lambda rail: rail.order)
        ordered_y = sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
        return tuple(
            Junction(
                x_rail_id=x_rail.rail_id,
                y_rail_id=y_rail.rail_id,
            )
            for x_rail in ordered_x
            for y_rail in ordered_y
        )


if __name__ == "__main__":
    unittest.main()
