from __future__ import annotations

import unittest

from toolsv2.adjacency import V1JunctionAdjacencyFinder
from toolsv2.definitions_loader import (
    LoadedDefinitions,
    LoadedGraphContent,
    load_v1_graph_content,
    load_v1_production_definitions,
)
from toolsv2.eligibility import V1CandidateEligibility
from toolsv2.geometry import V1JunctionGeometryBuildFeasibility
from toolsv2.graph_content import GraphContentModel, GraphContentNode, GraphContentRouteRequirement
from toolsv2.placement_solver import solve_placement_on_current_grid
from toolsv2.profile import build_minimum_active_grid
from toolsv2.production_node_definitions import (
    V1_AND_KNOT_KIND,
    V1_SKILL_FRAME_KIND,
    V1_SKILL_FRAME_TOP_PORT_ID,
)
from toolsv2.route_commit import V1RouteCommit
from toolsv2.route_orchestrator import V1RouteOrchestrator
from toolsv2.router import V1Router
from toolsv2.runtime_snapshot_builder import V1RuntimeSnapshotBuilder
from toolsv2.solver_types import LogicalYRailId, NodeId, PortId, RoutingPolicy
from toolsv2.visual_profiles import DEFAULT_AND_KNOT_PROFILE_KEY, DEFAULT_SKILL_FRAME_PROFILE_KEY


class DefinitionsLoaderTests(unittest.TestCase):
    def _policy(self) -> RoutingPolicy:
        return RoutingPolicy(
            policy_id="loaded_policy",
            rule_values=(
                ("allow_move_north", True),
                ("allow_move_south", True),
                ("allow_move_east", True),
                ("allow_move_west", True),
            ),
        )

    def test_loader_builds_canonical_definitions_and_visual_catalog(self) -> None:
        loaded = load_v1_production_definitions(
            {
                NodeId("skill_a"): V1_SKILL_FRAME_KIND,
                NodeId("and_a"): V1_AND_KNOT_KIND,
            }
        )

        self.assertIsInstance(loaded, LoadedDefinitions)
        self.assertEqual(
            DEFAULT_SKILL_FRAME_PROFILE_KEY,
            loaded.node_definitions[NodeId("skill_a")].render_profile.profile_key,
        )
        self.assertEqual(
            DEFAULT_AND_KNOT_PROFILE_KEY,
            loaded.node_definitions[NodeId("and_a")].render_profile.profile_key,
        )
        self.assertEqual(
            V1_SKILL_FRAME_TOP_PORT_ID,
            loaded.visual_profile_catalog.build_geometry_profile(
                DEFAULT_SKILL_FRAME_PROFILE_KEY
            ).ports[0].port_id,
        )

    def test_loader_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ValueError):
            load_v1_production_definitions(
                {
                    NodeId("unknown_a"): "mystery_kind",
                }
            )

    def test_loaded_node_definitions_mapping_is_immutable(self) -> None:
        loaded = load_v1_production_definitions(
            {
                NodeId("skill_a"): V1_SKILL_FRAME_KIND,
            }
        )

        with self.assertRaises(TypeError):
            loaded.node_definitions[NodeId("other")] = loaded.node_definitions[NodeId("skill_a")]  # type: ignore[index]

    def test_graph_content_loader_builds_solver_ready_data(self) -> None:
        loaded = load_v1_graph_content(
            GraphContentModel(
                routing_policy=self._policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("source"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
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
            )
        )

        self.assertIsInstance(loaded, LoadedGraphContent)
        self.assertEqual(2, len(loaded.node_definitions))
        self.assertEqual(2, len(loaded.node_metadata))
        self.assertEqual("loaded_policy", loaded.routing_policy.policy_id)
        self.assertEqual(
            (PortId("left"), PortId("right")),
            loaded.schema_view.source_port_keys(
                NodeId("source"),
                loaded.route_requirements[0],
            ),
        )

    def test_graph_content_loader_keeps_requirement_specific_allowances(self) -> None:
        loaded = load_v1_graph_content(
            GraphContentModel(
                routing_policy=self._policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("source"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_a"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink_b"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                ),
                route_requirements=(
                    GraphContentRouteRequirement(
                        requirement_id="req::a",
                        source_node_id=NodeId("source"),
                        sink_node_id=NodeId("sink_a"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("right"),),
                        sink_port_ids=(PortId("left"),),
                    ),
                    GraphContentRouteRequirement(
                        requirement_id="req::b",
                        source_node_id=NodeId("source"),
                        sink_node_id=NodeId("sink_b"),
                        requirement_kind="flow",
                        source_port_ids=(PortId("bottom"),),
                        sink_port_ids=(PortId("left"),),
                    ),
                ),
            )
        )

        self.assertEqual(
            (PortId("right"),),
            loaded.schema_view.source_port_keys(
                NodeId("source"),
                loaded.route_requirements[0],
            ),
        )
        self.assertEqual(
            (PortId("bottom"),),
            loaded.schema_view.source_port_keys(
                NodeId("source"),
                loaded.route_requirements[1],
            ),
        )

    def test_graph_content_can_flow_through_current_stack_end_to_end(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        loaded = load_v1_graph_content(
            GraphContentModel(
                routing_policy=self._policy(),
                nodes=(
                    GraphContentNode(
                        node_id=NodeId("source"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                    ),
                    GraphContentNode(
                        node_id=NodeId("sink"),
                        kind=V1_AND_KNOT_KIND,
                        authored_tier_y_rail_id=LogicalYRailId("tier_0"),
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
            )
        )

        placement_result = solve_placement_on_current_grid(
            active_grid=active_grid,
            routing_policy=loaded.routing_policy,
            node_definitions=loaded.node_definitions,
            node_metadata=loaded.node_metadata,
            ordered_same_row_groups=loaded.ordered_same_row_groups,
            port_requirements_by_node_id=loaded.port_requirements_by_node_id,
        )
        self.assertEqual("success", placement_result.status)

        initial_state = V1RuntimeSnapshotBuilder(
            active_grid=active_grid,
            node_definitions=loaded.node_definitions,
        )(placement_result.seeds[0])

        orchestrator = V1RouteOrchestrator(
            router=V1Router(
                adjacency_finder=V1JunctionAdjacencyFinder(
                    active_grid=active_grid,
                    visual_profile_catalog=loaded.visual_profile_catalog,
                ),
                geometry_build_feasibility=V1JunctionGeometryBuildFeasibility(
                    visual_profile_catalog=loaded.visual_profile_catalog,
                ),
                candidate_eligibility=V1CandidateEligibility(),
            ),
            commit=V1RouteCommit(),
        )

        result = orchestrator(
            initial_state,
            loaded.schema_view,
            loaded.route_requirements,
        )

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.final_state)
        self.assertEqual(1, len(result.final_state.objects.edges))


if __name__ == "__main__":
    unittest.main()
