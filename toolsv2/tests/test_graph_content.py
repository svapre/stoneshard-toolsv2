from __future__ import annotations

import unittest

from toolsv2.graph_content import (
    GraphContentModel,
    GraphContentNode,
    GraphContentOrderedSameRowGroup,
    GraphContentPortAttachmentRequirement,
    GraphContentRouteRequirement,
)
from toolsv2.solver_types import LogicalYRailId, NodeId, PortId, RoutingPolicy


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="content_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


class GraphContentTests(unittest.TestCase):
    def test_node_rejects_both_authored_and_dynamic_y_constraints(self) -> None:
        with self.assertRaises(ValueError):
            GraphContentNode(
                node_id=NodeId("a"),
                kind="skill_frame",
                authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                allowed_y_rail_ids=(LogicalYRailId("tier_0"),),
            )

    def test_route_requirement_rejects_empty_port_allowances(self) -> None:
        with self.assertRaises(ValueError):
            GraphContentRouteRequirement(
                requirement_id="req::a",
                source_node_id=NodeId("a"),
                sink_node_id=NodeId("b"),
                requirement_kind="flow",
                source_port_ids=(),
                sink_port_ids=(PortId("left"),),
            )

    def test_model_rejects_duplicate_nodes_and_same_row_duplicates(self) -> None:
        with self.assertRaises(ValueError):
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(node_id=NodeId("a"), kind="skill_frame"),
                    GraphContentNode(node_id=NodeId("a"), kind="and_knot"),
                ),
            )

        with self.assertRaises(ValueError):
            GraphContentModel(
                routing_policy=_policy(),
                nodes=(
                    GraphContentNode(node_id=NodeId("a"), kind="skill_frame"),
                    GraphContentNode(node_id=NodeId("b"), kind="and_knot"),
                ),
                ordered_same_row_groups=(
                    GraphContentOrderedSameRowGroup(
                        ordered_node_ids=(NodeId("a"), NodeId("b")),
                    ),
                    GraphContentOrderedSameRowGroup(
                        ordered_node_ids=(NodeId("b"),),
                    ),
                ),
            )

    def test_model_accepts_minimal_explicit_content(self) -> None:
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind="and_knot",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
            route_requirements=(
                GraphContentRouteRequirement(
                    requirement_id="req::a",
                    source_node_id=NodeId("a"),
                    sink_node_id=NodeId("a"),
                    requirement_kind="flow",
                    source_port_ids=(PortId("right"),),
                    sink_port_ids=(PortId("left"),),
                ),
            ),
            screening_port_requirements=(
                GraphContentPortAttachmentRequirement(
                    node_id=NodeId("a"),
                    port_id=PortId("right"),
                    required_attachments=1,
                ),
            ),
        )

        self.assertEqual(1, len(content.nodes))
        self.assertEqual("content_policy", content.routing_policy.policy_id)


if __name__ == "__main__":
    unittest.main()
