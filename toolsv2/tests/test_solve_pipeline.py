from __future__ import annotations

import unittest
from unittest.mock import patch

from toolsv2.graph_content import (
    GraphContentModel,
    GraphContentNode,
    GraphContentRouteRequirement,
)
from toolsv2.placement_solver import PlacementResult
from toolsv2.profile import build_minimum_active_grid
from toolsv2.production_node_definitions import V1_AND_KNOT_KIND, V1_SKILL_FRAME_KIND
from toolsv2.solve_pipeline import (
    CurrentGridSolveResult,
    build_v1_current_grid_solve_pipeline,
)
from toolsv2.solver_types import LogicalYRailId, NodeId, PortId, RoutingPolicy


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="pipeline_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


class SolvePipelineTests(unittest.TestCase):
    def test_current_grid_pipeline_succeeds_on_minimal_routeable_content(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a_source"),
                    kind=V1_AND_KNOT_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b_sink"),
                    kind=V1_AND_KNOT_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
            route_requirements=(
                GraphContentRouteRequirement(
                    requirement_id="req::source_to_sink",
                    source_node_id=NodeId("a_source"),
                    sink_node_id=NodeId("b_sink"),
                    requirement_kind="flow",
                    source_port_ids=(PortId("right"),),
                    sink_port_ids=(PortId("left"),),
                ),
            ),
        )

        result = build_v1_current_grid_solve_pipeline()(active_grid, content)

        self.assertIsInstance(result, CurrentGridSolveResult)
        self.assertEqual("success", result.status)
        self.assertEqual(active_grid, result.active_grid)
        self.assertEqual("success", result.placement_result.status)
        self.assertIsNotNone(result.placement_orchestration_result)
        self.assertEqual("success", result.placement_orchestration_result.status)
        self.assertIsNotNone(result.final_state)
        self.assertEqual(1, len(result.final_state.objects.edges))

    def test_current_grid_pipeline_reports_scoped_placement_failure(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
        )

        result = build_v1_current_grid_solve_pipeline()(active_grid, content)

        self.assertEqual("placement_failure_on_current_grid", result.status)
        self.assertEqual("failure_on_current_grid", result.placement_result.status)
        self.assertIsNone(result.placement_orchestration_result)
        self.assertIsNone(result.final_state)

    def test_current_grid_pipeline_reports_scoped_routing_failure(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a_source"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b_sink"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
            route_requirements=(
                GraphContentRouteRequirement(
                    requirement_id="req::north_to_north",
                    source_node_id=NodeId("a_source"),
                    sink_node_id=NodeId("b_sink"),
                    requirement_kind="flow",
                    source_port_ids=(PortId("top"),),
                    sink_port_ids=(PortId("top"),),
                ),
            ),
        )

        result = build_v1_current_grid_solve_pipeline()(active_grid, content)

        self.assertEqual("routing_failure_on_current_grid", result.status)
        self.assertEqual("success", result.placement_result.status)
        self.assertIsNotNone(result.placement_orchestration_result)
        self.assertEqual("failure_snapshot_set", result.placement_orchestration_result.status)
        self.assertEqual(1, len(result.placement_orchestration_result.attempts))
        self.assertIsNone(result.final_state)

    def test_current_grid_pipeline_forwards_max_seed_limit_to_placement_solver(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
        )

        with patch(
            "toolsv2.solve_pipeline.solve_placement_on_current_grid",
            return_value=PlacementResult(status="failure_on_current_grid"),
        ) as placement_mock:
            result = build_v1_current_grid_solve_pipeline(max_placement_seeds=2)(
                active_grid,
                content,
            )

        self.assertEqual("placement_failure_on_current_grid", result.status)
        self.assertEqual(2, placement_mock.call_args.kwargs["max_seeds"])

    def test_current_grid_pipeline_forwards_minimum_same_row_gap_to_placement_solver(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind=V1_SKILL_FRAME_KIND,
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
        )

        with patch(
            "toolsv2.solve_pipeline.solve_placement_on_current_grid",
            return_value=PlacementResult(status="failure_on_current_grid"),
        ) as placement_mock:
            result = build_v1_current_grid_solve_pipeline(minimum_same_row_gap=2)(
                active_grid,
                content,
            )

        self.assertEqual("placement_failure_on_current_grid", result.status)
        self.assertEqual(2, placement_mock.call_args.kwargs["minimum_same_row_gap"])


if __name__ == "__main__":
    unittest.main()
