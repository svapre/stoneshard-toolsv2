from __future__ import annotations

import unittest

from toolsv2.domain_builder import (
    NodePlacementMetadata,
    OrderedSameRowGroup,
    build_raw_domains,
)
from toolsv2.profile import build_minimum_active_grid, rebalance_band_dynamic_y_rails
from toolsv2.solver_types import NodeId


def _grid_with_seven_x_rails():
    return build_minimum_active_grid(
        default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
        authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
    )


def _x_projection(domain) -> tuple[str, ...]:
    return tuple(sorted({str(junction.x_rail_id) for junction in domain.junctions}))


def _y_projection(domain) -> tuple[str, ...]:
    return tuple(sorted({str(junction.y_rail_id) for junction in domain.junctions}))


class DomainBuilderTests(unittest.TestCase):
    def test_authored_tier_node_gets_singleton_dom_y(self) -> None:
        grid = _grid_with_seven_x_rails()
        domains = build_raw_domains(
            grid,
            node_metadata=(
                NodePlacementMetadata(
                    node_id=NodeId("node_a"),
                    authored_tier_y_rail_id=grid.y_rails[1].rail_id,
                ),
            ),
        )

        self.assertEqual(("tier_1",), _y_projection(domains[NodeId("node_a")]))
        self.assertEqual(len(grid.x_rails), len(domains[NodeId("node_a")].junctions))

    def test_dynamic_node_with_no_y_restriction_gets_all_active_y_rails(self) -> None:
        grid = _grid_with_seven_x_rails()
        band_id = grid.y_bands[0].band_id
        expanded_grid = rebalance_band_dynamic_y_rails(grid, band_id, ("dyn_mid",))

        domains = build_raw_domains(
            expanded_grid,
            node_metadata=(
                NodePlacementMetadata(node_id=NodeId("node_dyn")),
            ),
        )

        self.assertEqual(
            tuple(rail.rail_id for rail in expanded_grid.y_rails),
            tuple(
                rail.rail_id
                for rail in expanded_grid.y_rails
                if str(rail.rail_id) in set(_y_projection(domains[NodeId("node_dyn")]))
            ),
        )
        self.assertEqual(
            len(expanded_grid.x_rails) * len(expanded_grid.y_rails),
            len(domains[NodeId("node_dyn")].junctions),
        )

    def test_four_ordered_nodes_on_seven_rails_collapse_to_unique_pattern(self) -> None:
        grid = _grid_with_seven_x_rails()
        domains = build_raw_domains(
            grid,
            node_metadata=(
                NodePlacementMetadata(node_id=NodeId("n0")),
                NodePlacementMetadata(node_id=NodeId("n1")),
                NodePlacementMetadata(node_id=NodeId("n2")),
                NodePlacementMetadata(node_id=NodeId("n3")),
            ),
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("n0"), NodeId("n1"), NodeId("n2"), NodeId("n3")),
                ),
            ),
        )

        self.assertEqual(("x0",), _x_projection(domains[NodeId("n0")]))
        self.assertEqual(("x2",), _x_projection(domains[NodeId("n1")]))
        self.assertEqual(("x4",), _x_projection(domains[NodeId("n2")]))
        self.assertEqual(("x6",), _x_projection(domains[NodeId("n3")]))

    def test_three_ordered_nodes_on_seven_rails_get_safe_left_middle_right_domains(self) -> None:
        grid = _grid_with_seven_x_rails()
        domains = build_raw_domains(
            grid,
            node_metadata=(
                NodePlacementMetadata(node_id=NodeId("left")),
                NodePlacementMetadata(node_id=NodeId("middle")),
                NodePlacementMetadata(node_id=NodeId("right")),
            ),
            ordered_same_row_groups=(
                OrderedSameRowGroup(
                    ordered_node_ids=(NodeId("left"), NodeId("middle"), NodeId("right")),
                ),
            ),
        )

        self.assertEqual(
            ("x0", "x1", "x2"),
            _x_projection(domains[NodeId("left")]),
        )
        self.assertEqual(
            ("x2", "x3", "x4"),
            _x_projection(domains[NodeId("middle")]),
        )
        self.assertEqual(
            ("x4", "x5", "x6"),
            _x_projection(domains[NodeId("right")]),
        )

    def test_unsupported_row_shape_fails_loudly(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5"),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        with self.assertRaises(NotImplementedError):
            build_raw_domains(
                grid,
                node_metadata=(
                    NodePlacementMetadata(node_id=NodeId("a")),
                    NodePlacementMetadata(node_id=NodeId("b")),
                    NodePlacementMetadata(node_id=NodeId("c")),
                ),
                ordered_same_row_groups=(
                    OrderedSameRowGroup(
                        ordered_node_ids=(NodeId("a"), NodeId("b"), NodeId("c")),
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
