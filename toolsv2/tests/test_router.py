from __future__ import annotations

import unittest

from toolsv2.adjacency import V1JunctionAdjacencyFinder
from toolsv2.eligibility import (
    RouteRequirementPortAllowance,
    StaticRouteRequirementSchemaView,
    V1CandidateEligibility,
)
from toolsv2.geometry import V1JunctionGeometryBuildFeasibility
from toolsv2.profile import build_minimum_active_grid
from toolsv2.router import V1Router
from toolsv2.solver_types import (
    Port,
    PortEdge,
    PortEdgeId,
    PortGraphIndex,
    PortGraphState,
    PortId,
    PortRef,
    RouteRequirement,
    RuntimeNode,
    RuntimeObjectSet,
    build_runtime_junctions_for_active_grid,
    NodeId,
)


class RouterTests(unittest.TestCase):
    def _build_router_for_grid(self, grid) -> V1Router:
        return V1Router(
            adjacency_finder=V1JunctionAdjacencyFinder(active_grid=grid),
            geometry_build_feasibility=V1JunctionGeometryBuildFeasibility(),
            candidate_eligibility=V1CandidateEligibility(),
        )

    def test_router_succeeds_when_source_and_sink_are_immediately_reachable(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(left_junction, right_junction),
            ),
        )
        router = self._build_router_for_grid(grid)
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=left_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=right_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::junctions",
            source_object_ref=left_junction.junction_id,
            sink_object_ref=right_junction.junction_id,
            requirement_kind="flow",
        )

        result = router(state, schema_view, route_requirement)

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.route_plan)
        self.assertEqual(
            PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("west"),
            ),
            result.route_plan.reached_sink_port_ref,
        )
        self.assertEqual(1, len(result.route_plan.steps))
        self.assertEqual("tentative_connection", result.route_plan.steps[0].step_kind)

    def test_router_traverses_existing_bidirectional_edges_via_entry_context(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::source_to_sink")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=source_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                        traversal_mode="bidirectional",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                edge_ids=(edge_id,),
            ),
        )
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        router = self._build_router_for_grid(grid)
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("source_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::nodes",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        result = router(state, schema_view, route_requirement)

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.route_plan)
        self.assertEqual(1, len(result.route_plan.steps))
        self.assertEqual("built_edge", result.route_plan.steps[0].step_kind)
        self.assertEqual(edge_id, result.route_plan.steps[0].via_edge_id)

    def test_router_fails_cleanly_when_no_valid_sink_port_is_reachable(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::reverse_only")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=source_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                        traversal_mode="b_to_a",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                edge_ids=(edge_id,),
            ),
        )
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        router = self._build_router_for_grid(grid)
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("source_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::nodes",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        result = router(state, schema_view, route_requirement)

        self.assertEqual("failure_snapshot", result.status)
        self.assertIsNone(result.route_plan)

    def test_router_does_not_mutate_committed_runtime_state_during_search(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(left_junction, right_junction),
            ),
        )
        original_state = state
        router = self._build_router_for_grid(grid)
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=left_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=right_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::junctions",
            source_object_ref=left_junction.junction_id,
            sink_object_ref=right_junction.junction_id,
            requirement_kind="flow",
        )

        result = router(state, schema_view, route_requirement)

        self.assertEqual("success", result.status)
        self.assertEqual(original_state, state)
        self.assertEqual((), state.objects.edges)

    def test_router_failure_is_scoped_to_current_snapshot_only(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::nodes",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("source_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        failing_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::reverse_only"),
                        port_ref_a=source_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                        traversal_mode="b_to_a",
                    ),
                ),
            ),
            graph=PortGraphIndex(edge_ids=(PortEdgeId("edge::reverse_only"),)),
        )
        succeeding_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::forward_only"),
                        port_ref_a=source_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                ),
            ),
            graph=PortGraphIndex(edge_ids=(PortEdgeId("edge::forward_only"),)),
        )
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        router = self._build_router_for_grid(grid)

        failing_result = router(failing_state, schema_view, route_requirement)
        succeeding_result = router(succeeding_state, schema_view, route_requirement)

        self.assertEqual("failure_snapshot", failing_result.status)
        self.assertEqual("success", succeeding_result.status)

    def test_no_commit_update_behavior_is_embedded_in_router(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(left_junction, right_junction),
            ),
        )
        router = self._build_router_for_grid(grid)
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=left_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=right_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::junctions",
            source_object_ref=left_junction.junction_id,
            sink_object_ref=right_junction.junction_id,
            requirement_kind="flow",
        )

        result = router(state, schema_view, route_requirement)

        self.assertEqual("success", result.status)
        self.assertEqual((), state.objects.edges)
        self.assertEqual("tentative_connection", result.route_plan.steps[0].step_kind)
        self.assertIsNone(result.route_plan.steps[0].via_edge_id)


if __name__ == "__main__":
    unittest.main()
