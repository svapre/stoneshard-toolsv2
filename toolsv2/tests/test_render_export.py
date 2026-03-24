from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toolsv2.graph_content import GraphContentModel, GraphContentNode, GraphContentRouteRequirement
from toolsv2.profile import build_minimum_active_grid
from toolsv2.render_export import (
    render_v1_base_state,
    render_v1_successful_solve_result,
    save_base_render_result,
)
from toolsv2.runtime_snapshot_builder import build_v1_runtime_snapshot_builder
from toolsv2.placement_solver import PlacementSeed
from toolsv2.production_node_definitions import (
    V1_AND_KNOT_KIND,
    build_v1_and_knot_node_definition,
    build_v1_production_visual_profile_catalog,
)
from toolsv2.solve_pipeline import build_v1_current_grid_solve_pipeline
from toolsv2.solver_common import Junction, NodeDomain, NodeId, PortId, RoutingPolicy


class RenderExportTests(unittest.TestCase):
    def _build_seed(self, assignments: dict[NodeId, Junction]) -> PlacementSeed:
        return PlacementSeed(
            domains={
                node_id: NodeDomain(node_id=node_id, junctions=frozenset({junction}))
                for node_id, junction in assignments.items()
            },
            assignments=assignments,
        )

    def _policy(self) -> RoutingPolicy:
        return RoutingPolicy(
            policy_id="render_export_policy",
            rule_values=(
                ("allow_move_north", True),
                ("allow_move_south", True),
                ("allow_move_east", True),
                ("allow_move_west", True),
            ),
        )

    def test_render_v1_base_state_renders_and_saves_png(self) -> None:
        node_id = NodeId("and_a")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {node_id: build_v1_and_knot_node_definition(node_id)},
        )(
            self._build_seed(
                {
                    node_id: Junction(x_rail_id="x0", y_rail_id="tier_0"),
                }
            )
        )

        result = render_v1_base_state(
            active_grid=active_grid,
            state=state,
            visual_profile_catalog=build_v1_production_visual_profile_catalog(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = save_base_render_result(result, Path(temp_dir) / "base.png")
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 0)

    def test_render_v1_successful_solve_result_renders_and_saves_png(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )
        solve_result = build_v1_current_grid_solve_pipeline()( 
            active_grid,
            GraphContentModel(
                routing_policy=self._policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("source"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id="tier_0",
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id="tier_0",
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::source_to_sink",
                        source_node_id=NodeId("source"),
                        sink_node_id=NodeId("sink"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("left"), PortId("right")),
                        sink_port_ids=(PortId("left"), PortId("right")),
                    ),
                ),
            ),
        )

        self.assertEqual("success", solve_result.status)
        result = render_v1_successful_solve_result(solve_result)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = save_base_render_result(result, Path(temp_dir) / "solve_base.png")
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
