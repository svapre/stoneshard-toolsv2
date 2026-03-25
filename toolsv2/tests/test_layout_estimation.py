from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.graph_content import GraphContentModel, GraphContentNode, GraphContentRouteRequirement
from toolsv2.layout_estimation import (
    V1RuleBasedLayoutDemandEstimator,
    build_adjacent_authored_flow_band_rule,
    build_single_sink_mediated_band_rule,
    build_same_band_multi_sink_split_pattern_rule,
)
from toolsv2.layout_profiles import (
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    build_v1_vanilla_skill_tree_layout_profile,
)
from toolsv2.production_node_definitions import V1_AND_KNOT_KIND, V1_SKILL_FRAME_KIND
from toolsv2.solver_types import LogicalYRailId, NodeId, PortId, RoutingPolicy


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="layout_estimation_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


class LayoutEstimationTests(unittest.TestCase):
    def test_rule_based_estimator_keeps_base_grid_when_no_demands_apply(self) -> None:
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=build_v1_vanilla_skill_tree_layout_profile(),
            authored_tier_rail_ids=(LogicalYRailId("tier_0"), LogicalYRailId("tier_1")),
        )

        estimate = estimator(
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("skill_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("skill_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                ),
            )
        )

        self.assertEqual((), estimate.band_layout_demands)
        self.assertEqual(
            ("tier_0", "tier_1"),
            tuple(str(rail.rail_id) for rail in estimate.initial_grid.y_rails),
        )

    def test_same_band_multi_sink_split_rule_demands_initial_split_pair(self) -> None:
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=build_v1_vanilla_skill_tree_layout_profile(),
            authored_tier_rail_ids=(LogicalYRailId("tier_0"), LogicalYRailId("tier_1")),
            band_layout_demand_rules=(
                build_same_band_multi_sink_split_pattern_rule(
                    split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                ),
            ),
        )

        estimate = estimator(
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("input_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("and_0"),
                        kind=V1_AND_KNOT_KIND,
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::input_a_to_and",
                        source_node_id=NodeId("input_a"),
                        sink_node_id=NodeId("and_0"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::and_to_sink_a",
                        source_node_id=NodeId("and_0"),
                        sink_node_id=NodeId("sink_a"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::and_to_sink_b",
                        source_node_id=NodeId("and_0"),
                        sink_node_id=NodeId("sink_b"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                ),
            )
        )

        self.assertEqual(1, len(estimate.band_layout_demands))
        demand = estimate.band_layout_demands[0]
        self.assertEqual(V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID, demand.pattern_id)
        self.assertEqual(
            ("tier_0", "dyn::tier_0::tier_1::0", "dyn::tier_0::tier_1::1", "tier_1"),
            tuple(str(rail.rail_id) for rail in estimate.initial_grid.y_rails),
        )
        dynamic_ranks = {
            str(rail.rail_id): rail.logical_rank
            for rail in estimate.initial_grid.y_rails
            if rail.kind == "dynamic"
        }
        self.assertEqual(Fraction(3, 7), dynamic_ranks["dyn::tier_0::tier_1::0"])
        self.assertEqual(Fraction(4, 7), dynamic_ranks["dyn::tier_0::tier_1::1"])

    def test_adjacent_authored_flow_rule_demands_single_mid_band(self) -> None:
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=build_v1_vanilla_skill_tree_layout_profile(),
            authored_tier_rail_ids=(
                LogicalYRailId("tier_0"),
                LogicalYRailId("tier_1"),
                LogicalYRailId("tier_2"),
            ),
            band_layout_demand_rules=(
                build_adjacent_authored_flow_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
            ),
        )

        estimate = estimator(
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("skill_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("skill_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_2"),
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::skill_a_to_skill_b",
                        source_node_id=NodeId("skill_a"),
                        sink_node_id=NodeId("skill_b"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                ),
            )
        )

        self.assertEqual(1, len(estimate.band_layout_demands))
        demand = estimate.band_layout_demands[0]
        self.assertEqual(V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID, demand.pattern_id)
        self.assertEqual(
            ("tier_0", "tier_1", "dyn::tier_1::tier_2::0", "tier_2"),
            tuple(str(rail.rail_id) for rail in estimate.initial_grid.y_rails),
        )

    def test_estimator_resolves_same_band_single_mid_to_split_pair(self) -> None:
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=build_v1_vanilla_skill_tree_layout_profile(),
            authored_tier_rail_ids=(LogicalYRailId("tier_0"), LogicalYRailId("tier_1")),
            band_layout_demand_rules=(
                build_adjacent_authored_flow_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
                build_same_band_multi_sink_split_pattern_rule(
                    split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                ),
            ),
        )

        estimate = estimator(
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("root_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("root_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("root_c"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("and_0"),
                        kind=V1_AND_KNOT_KIND,
                        allowed_y_rail_ids=(
                            LogicalYRailId("dyn::tier_0::tier_1::0"),
                            LogicalYRailId("dyn::tier_0::tier_1::1"),
                        ),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_c"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::root_a_to_and",
                        source_node_id=NodeId("root_a"),
                        sink_node_id=NodeId("and_0"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::root_b_to_and",
                        source_node_id=NodeId("root_b"),
                        sink_node_id=NodeId("and_0"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("left"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::and_to_sink_a",
                        source_node_id=NodeId("and_0"),
                        sink_node_id=NodeId("sink_a"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::and_to_sink_b",
                        source_node_id=NodeId("and_0"),
                        sink_node_id=NodeId("sink_b"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::root_c_to_sink_c",
                        source_node_id=NodeId("root_c"),
                        sink_node_id=NodeId("sink_c"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                ),
            )
        )

        self.assertEqual(1, len(estimate.band_layout_demands))
        demand = estimate.band_layout_demands[0]
        self.assertEqual(V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID, demand.pattern_id)
        self.assertEqual(
            ("tier_0", "dyn::tier_0::tier_1::0", "dyn::tier_0::tier_1::1", "tier_1"),
            tuple(str(rail.rail_id) for rail in estimate.initial_grid.y_rails),
        )

    def test_single_sink_mediated_band_rule_anchors_gate_to_sink_adjacent_band(self) -> None:
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=build_v1_vanilla_skill_tree_layout_profile(),
            authored_tier_rail_ids=(
                LogicalYRailId("tier_0"),
                LogicalYRailId("tier_1"),
                LogicalYRailId("tier_2"),
            ),
            band_layout_demand_rules=(
                build_single_sink_mediated_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
            ),
        )

        estimate = estimator(
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("root_a"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("root_b"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("and_0"),
                        kind=V1_AND_KNOT_KIND,
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_x"),
                        kind=V1_SKILL_FRAME_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_2"),
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::root_a_to_and",
                        source_node_id=NodeId("root_a"),
                        sink_node_id=NodeId("and_0"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("left"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::root_b_to_and",
                        source_node_id=NodeId("root_b"),
                        sink_node_id=NodeId("and_0"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("right"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::and_to_sink_x",
                        source_node_id=NodeId("and_0"),
                        sink_node_id=NodeId("sink_x"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("top"),),
                    ),
                ),
            )
        )

        self.assertEqual(1, len(estimate.band_layout_demands))
        demand = estimate.band_layout_demands[0]
        self.assertEqual(V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID, demand.pattern_id)
        self.assertEqual(
            ("tier_0", "tier_1", "dyn::tier_1::tier_2::0", "tier_2"),
            tuple(str(rail.rail_id) for rail in estimate.initial_grid.y_rails),
        )


if __name__ == "__main__":
    unittest.main()
