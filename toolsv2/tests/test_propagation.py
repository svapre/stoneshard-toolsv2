from __future__ import annotations

import unittest

from toolsv2.domain_builder import NodePlacementMetadata, OrderedSameRowGroup
from toolsv2.profile import build_minimum_active_grid
from toolsv2.propagation import propagate_domains
from toolsv2.solver_types import Junction, NodeDomain, NodeId


def _grid_with_seven_x_rails():
    return build_minimum_active_grid(
        default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
        authored_tier_rail_ids=("tier_0", "tier_1"),
    )


def _grid_with_x_rails(*x_rail_ids: str):
    return build_minimum_active_grid(
        default_x_rail_ids=x_rail_ids,
        authored_tier_rail_ids=("tier_0", "tier_1"),
    )


def _domain(node_id: NodeId, junctions: tuple[Junction, ...]) -> NodeDomain:
    return NodeDomain(node_id=node_id, junctions=frozenset(junctions))


def _x_projection(domain: NodeDomain) -> tuple[str, ...]:
    return tuple(sorted({str(junction.x_rail_id) for junction in domain.junctions}))


def _y_projection(domain: NodeDomain) -> tuple[str, ...]:
    return tuple(sorted({str(junction.y_rail_id) for junction in domain.junctions}))


class PropagationTests(unittest.TestCase):
    def test_occupancy_removes_fixed_junction_from_other_node(self) -> None:
        grid = _grid_with_seven_x_rails()
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("fixed"): _domain(
                    NodeId("fixed"),
                    (Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),),
                ),
                NodeId("other"): _domain(
                    NodeId("other"),
                    (
                        Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),
                        Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id),
                    ),
                ),
            },
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(
            ("x1",),
            _x_projection(result.domains[NodeId("other")]),
        )

    def test_singleton_collapse_triggers_further_reductions(self) -> None:
        grid = _grid_with_seven_x_rails()
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("left"): _domain(
                    NodeId("left"),
                    (Junction(grid.x_rails[0].rail_id, tier_0),),
                ),
                NodeId("middle"): _domain(
                    NodeId("middle"),
                    (
                        Junction(grid.x_rails[2].rail_id, tier_0),
                        Junction(grid.x_rails[3].rail_id, tier_0),
                        Junction(grid.x_rails[4].rail_id, tier_0),
                    ),
                ),
                NodeId("right"): _domain(
                    NodeId("right"),
                    (Junction(grid.x_rails[4].rail_id, tier_0),),
                ),
                NodeId("other"): _domain(
                    NodeId("other"),
                    (
                        Junction(grid.x_rails[2].rail_id, tier_0),
                        Junction(grid.x_rails[3].rail_id, tier_0),
                    ),
                ),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("left"), NodeId("middle"), NodeId("right")),
                ),
            ),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(
            ("x2",),
            _x_projection(result.domains[NodeId("middle")]),
        )
        self.assertEqual(
            ("x3",),
            _x_projection(result.domains[NodeId("other")]),
        )

    def test_three_node_row_domains_shrink_under_support_checks(self) -> None:
        grid = _grid_with_seven_x_rails()
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("left"): _domain(
                    NodeId("left"),
                    (
                        Junction(grid.x_rails[1].rail_id, tier_0),
                        Junction(grid.x_rails[2].rail_id, tier_0),
                    ),
                ),
                NodeId("middle"): _domain(
                    NodeId("middle"),
                    (
                        Junction(grid.x_rails[2].rail_id, tier_0),
                        Junction(grid.x_rails[3].rail_id, tier_0),
                        Junction(grid.x_rails[4].rail_id, tier_0),
                    ),
                ),
                NodeId("right"): _domain(
                    NodeId("right"),
                    (
                        Junction(grid.x_rails[4].rail_id, tier_0),
                        Junction(grid.x_rails[5].rail_id, tier_0),
                    ),
                ),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("left"), NodeId("middle"), NodeId("right")),
                ),
            ),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(
            ("x1",),
            _x_projection(result.domains[NodeId("left")]),
        )
        self.assertEqual(
            ("x3",),
            _x_projection(result.domains[NodeId("middle")]),
        )
        self.assertEqual(
            ("x5",),
            _x_projection(result.domains[NodeId("right")]),
        )

    def test_four_node_unique_row_pattern_remains_stable(self) -> None:
        grid = _grid_with_seven_x_rails()
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("n0"): _domain(NodeId("n0"), (Junction(grid.x_rails[0].rail_id, tier_0),)),
                NodeId("n1"): _domain(NodeId("n1"), (Junction(grid.x_rails[2].rail_id, tier_0),)),
                NodeId("n2"): _domain(NodeId("n2"), (Junction(grid.x_rails[4].rail_id, tier_0),)),
                NodeId("n3"): _domain(NodeId("n3"), (Junction(grid.x_rails[6].rail_id, tier_0),)),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("n0"), NodeId("n1"), NodeId("n2"), NodeId("n3")),
                ),
            ),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(
            ("x0",),
            _x_projection(result.domains[NodeId("n0")]),
        )
        self.assertEqual(
            ("x2",),
            _x_projection(result.domains[NodeId("n1")]),
        )
        self.assertEqual(
            ("x4",),
            _x_projection(result.domains[NodeId("n2")]),
        )
        self.assertEqual(
            ("x6",),
            _x_projection(result.domains[NodeId("n3")]),
        )

    def test_contradiction_is_reported_when_domain_becomes_empty(self) -> None:
        grid = _grid_with_seven_x_rails()
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("a"): _domain(
                    NodeId("a"),
                    (Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),),
                ),
                NodeId("b"): _domain(
                    NodeId("b"),
                    (Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id),),
                ),
            },
        )

        self.assertTrue(result.has_contradiction)
        self.assertIn(NodeId("a"), result.contradiction_node_ids)
        self.assertIn(NodeId("b"), result.contradiction_node_ids)

    def test_three_node_row_supports_six_x_rails(self) -> None:
        grid = _grid_with_x_rails("x0", "x1", "x2", "x3", "x4", "x5")
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("left"): _domain(
                    NodeId("left"),
                    (
                        Junction(grid.x_rails[1].rail_id, tier_0),
                        Junction(grid.x_rails[2].rail_id, tier_0),
                    ),
                ),
                NodeId("middle"): _domain(
                    NodeId("middle"),
                    (
                        Junction(grid.x_rails[2].rail_id, tier_0),
                        Junction(grid.x_rails[3].rail_id, tier_0),
                    ),
                ),
                NodeId("right"): _domain(
                    NodeId("right"),
                    (
                        Junction(grid.x_rails[4].rail_id, tier_0),
                        Junction(grid.x_rails[5].rail_id, tier_0),
                    ),
                ),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("left"), NodeId("middle"), NodeId("right")),
                ),
            ),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(("x1",), _x_projection(result.domains[NodeId("left")]))
        self.assertEqual(("x3",), _x_projection(result.domains[NodeId("middle")]))
        self.assertEqual(("x5",), _x_projection(result.domains[NodeId("right")]))

    def test_impossible_ordered_row_shape_reports_contradiction(self) -> None:
        grid = _grid_with_x_rails("x0", "x1", "x2", "x3", "x4", "x5")
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("n0"): _domain(
                    NodeId("n0"),
                    tuple(
                        Junction(x_rail.rail_id, tier_0)
                        for x_rail in grid.x_rails
                    ),
                ),
                NodeId("n1"): _domain(
                    NodeId("n1"),
                    tuple(
                        Junction(x_rail.rail_id, tier_0)
                        for x_rail in grid.x_rails
                    ),
                ),
                NodeId("n2"): _domain(
                    NodeId("n2"),
                    tuple(
                        Junction(x_rail.rail_id, tier_0)
                        for x_rail in grid.x_rails
                    ),
                ),
                NodeId("n3"): _domain(
                    NodeId("n3"),
                    tuple(
                        Junction(x_rail.rail_id, tier_0)
                        for x_rail in grid.x_rails
                    ),
                ),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("n0"), NodeId("n1"), NodeId("n2"), NodeId("n3")),
                ),
            ),
        )

        self.assertTrue(result.has_contradiction)
        self.assertEqual(
            (NodeId("n0"), NodeId("n1"), NodeId("n2"), NodeId("n3")),
            result.contradiction_node_ids,
        )

    def test_ordered_row_propagation_can_use_non_vanilla_minimum_gap(self) -> None:
        grid = _grid_with_seven_x_rails()
        tier_0 = grid.y_rails[0].rail_id
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("left"): _domain(
                    NodeId("left"),
                    tuple(
                        Junction(grid.x_rails[index].rail_id, tier_0)
                        for index in (0, 1)
                    ),
                ),
                NodeId("middle"): _domain(
                    NodeId("middle"),
                    tuple(
                        Junction(grid.x_rails[index].rail_id, tier_0)
                        for index in (2, 3, 4)
                    ),
                ),
                NodeId("right"): _domain(
                    NodeId("right"),
                    tuple(
                        Junction(grid.x_rails[index].rail_id, tier_0)
                        for index in (5, 6)
                    ),
                ),
            },
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("left"), NodeId("middle"), NodeId("right")),
                ),
            ),
            minimum_same_row_gap=2,
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(("x0",), _x_projection(result.domains[NodeId("left")]))
        self.assertEqual(("x3",), _x_projection(result.domains[NodeId("middle")]))
        self.assertEqual(("x6",), _x_projection(result.domains[NodeId("right")]))

    def test_tier_propagation_intersects_y_domain(self) -> None:
        grid = _grid_with_seven_x_rails()
        result = propagate_domains(
            active_grid=grid,
            domains={
                NodeId("tiered"): _domain(
                    NodeId("tiered"),
                    tuple(
                        Junction(x_rail.rail_id, y_rail.rail_id)
                        for x_rail in grid.x_rails
                        for y_rail in grid.y_rails
                    ),
                ),
            },
            node_metadata=(
                NodePlacementMetadata(
                    node_id=NodeId("tiered"),
                    authored_tier_y_rail_id=grid.y_rails[1].rail_id,
                ),
            ),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(
            ("tier_1",),
            _y_projection(result.domains[NodeId("tiered")]),
        )


if __name__ == "__main__":
    unittest.main()
