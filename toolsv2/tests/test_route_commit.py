from __future__ import annotations

import unittest

from toolsv2.entry_queries import directly_reachable_next_entry_contexts
from toolsv2.profile import build_minimum_active_grid
from toolsv2.route_commit import V1RouteCommit
from toolsv2.router import TentativeRoutePlan, TentativeRouteStep, V1Router
from toolsv2.adjacency import V1JunctionAdjacencyFinder
from toolsv2.geometry import V1JunctionGeometryBuildFeasibility
from toolsv2.eligibility import (
    RouteRequirementPortAllowance,
    StaticRouteRequirementSchemaView,
    V1CandidateEligibility,
)
from toolsv2.solver_types import (
    EntryContext,
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


class RouteCommitTests(unittest.TestCase):
    def _build_junction_router(self, grid) -> V1Router:
        return V1Router(
            adjacency_finder=V1JunctionAdjacencyFinder(active_grid=grid),
            geometry_build_feasibility=V1JunctionGeometryBuildFeasibility(),
            candidate_eligibility=V1CandidateEligibility(),
        )

    def test_successful_commit_returns_new_snapshot_without_mutating_original(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        current_state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(left_junction, right_junction),
            ),
        )
        router = self._build_junction_router(grid)
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
        route_plan = router(current_state, schema_view, route_requirement).route_plan
        committer = V1RouteCommit()

        result = committer(current_state, route_plan)

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.new_state)
        self.assertEqual((), current_state.objects.edges)
        self.assertEqual(1, len(result.added_edges))
        self.assertEqual(1, len(result.new_state.objects.edges))
        self.assertEqual(
            result.added_edges[0].edge_id,
            result.new_state.objects.edges[0].edge_id,
        )

    def test_local_invalid_tentative_route_is_rejected(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        current_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
            ),
        )
        route_plan = TentativeRoutePlan(
            route_requirement_id="req::invalid",
            start_entry_context=EntryContext(
                current_port_ref=left_port_ref,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="built_edge",
                    from_entry_context=EntryContext(
                        current_port_ref=left_port_ref,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=right_port_ref,
                        incoming_edge_id=PortEdgeId("edge::missing"),
                    ),
                    via_edge_id=PortEdgeId("edge::missing"),
                ),
            ),
            reached_sink_port_ref=right_port_ref,
        )

        result = V1RouteCommit()(current_state, route_plan)

        self.assertEqual("failure_snapshot", result.status)
        self.assertIsNone(result.new_state)

    def test_commit_does_not_own_cross_source_reachability_validation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        junction_b, junction_c = build_runtime_junctions_for_active_grid(grid)
        node_a_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        junction_b_west = PortRef(
            owner_ref=junction_b.junction_id,
            owner_local_key=PortId("west"),
        )
        junction_c_west = PortRef(
            owner_ref=junction_c.junction_id,
            owner_local_key=PortId("west"),
        )
        current_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=node_a_port_ref),),
                    ),
                ),
                junctions=(junction_b, junction_c),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::a_to_b"),
                        port_ref_a=node_a_port_ref,
                        port_ref_b=junction_b_west,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                ),
            ),
            graph=PortGraphIndex(edge_ids=(PortEdgeId("edge::a_to_b"),)),
        )
        route_plan = TentativeRoutePlan(
            route_requirement_id="req::b_to_c",
            start_entry_context=EntryContext(
                current_port_ref=junction_b_west,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=EntryContext(
                        current_port_ref=junction_b_west,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=junction_c_west,
                        incoming_edge_id=None,
                    ),
                ),
            ),
            reached_sink_port_ref=junction_c_west,
        )

        result = V1RouteCommit()(current_state, route_plan)

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.new_state)

    def test_bidirectional_and_unidirectional_materialization_are_respected(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        current_state = PortGraphState(
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
            ),
        )
        bidirectional_plan = TentativeRoutePlan(
            route_requirement_id="req::bi",
            start_entry_context=EntryContext(
                current_port_ref=source_port_ref,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=EntryContext(
                        current_port_ref=source_port_ref,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=sink_port_ref,
                        incoming_edge_id=None,
                    ),
                    new_edge_traversal_mode="bidirectional",
                ),
            ),
            reached_sink_port_ref=sink_port_ref,
        )
        unidirectional_plan = TentativeRoutePlan(
            route_requirement_id="req::uni",
            start_entry_context=EntryContext(
                current_port_ref=source_port_ref,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=EntryContext(
                        current_port_ref=source_port_ref,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=sink_port_ref,
                        incoming_edge_id=None,
                    ),
                    new_edge_traversal_mode="a_to_b",
                ),
            ),
            reached_sink_port_ref=sink_port_ref,
        )
        committer = V1RouteCommit()

        bidirectional_result = committer(current_state, bidirectional_plan)
        unidirectional_result = committer(current_state, unidirectional_plan)

        self.assertEqual("success", bidirectional_result.status)
        self.assertEqual("bidirectional", bidirectional_result.added_edges[0].traversal_mode)
        self.assertEqual("success", unidirectional_result.status)
        self.assertEqual("a_to_b", unidirectional_result.added_edges[0].traversal_mode)
        self.assertEqual(
            1,
            len(
                directly_reachable_next_entry_contexts(
                    bidirectional_result.new_state,
                    EntryContext(current_port_ref=source_port_ref, incoming_edge_id=None),
                )
            ),
        )
        self.assertEqual(
            1,
            len(
                directly_reachable_next_entry_contexts(
                    bidirectional_result.new_state,
                    EntryContext(current_port_ref=sink_port_ref, incoming_edge_id=None),
                )
            ),
        )
        self.assertEqual(
            1,
            len(
                directly_reachable_next_entry_contexts(
                    unidirectional_result.new_state,
                    EntryContext(current_port_ref=source_port_ref, incoming_edge_id=None),
                )
            ),
        )
        self.assertEqual(
            (),
            directly_reachable_next_entry_contexts(
                unidirectional_result.new_state,
                EntryContext(current_port_ref=sink_port_ref, incoming_edge_id=None),
            ),
        )

    def test_commit_failure_is_scoped_to_current_snapshot_and_current_route_only(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        junction_b, junction_c = build_runtime_junctions_for_active_grid(grid)
        node_a_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        junction_b_west = PortRef(
            owner_ref=junction_b.junction_id,
            owner_local_key=PortId("west"),
        )
        junction_c_west = PortRef(
            owner_ref=junction_c.junction_id,
            owner_local_key=PortId("west"),
        )
        route_plan = TentativeRoutePlan(
            route_requirement_id="req::b_to_c",
            start_entry_context=EntryContext(
                current_port_ref=junction_b_west,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=EntryContext(
                        current_port_ref=junction_b_west,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=junction_c_west,
                        incoming_edge_id=None,
                    ),
                ),
            ),
            reached_sink_port_ref=junction_c_west,
        )
        conflicting_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=node_a_port_ref),),
                    ),
                ),
                junctions=(junction_b, junction_c),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::a_to_b"),
                        port_ref_a=node_a_port_ref,
                        port_ref_b=junction_b_west,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                ),
            ),
            graph=PortGraphIndex(edge_ids=(PortEdgeId("edge::a_to_b"),)),
        )
        clean_state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(junction_b, junction_c),
            ),
        )
        committer = V1RouteCommit()

        conflicting_result = committer(conflicting_state, route_plan)
        clean_result = committer(clean_state, route_plan)

        self.assertEqual("success", conflicting_result.status)
        self.assertEqual("success", clean_result.status)

    def test_commit_rejects_new_attachment_when_finite_port_capacity_is_full(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        existing_port_ref = PortRef(
            owner_ref=NodeId("existing_node"),
            owner_local_key=PortId("east"),
        )
        current_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref, capacity=1),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("existing_node"),
                        ports=(Port(port_ref=existing_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::existing_to_sink"),
                        port_ref_a=existing_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                    ),
                ),
            ),
            graph=PortGraphIndex(edge_ids=(PortEdgeId("edge::existing_to_sink"),)),
        )
        route_plan = TentativeRoutePlan(
            route_requirement_id="req::capacity",
            start_entry_context=EntryContext(
                current_port_ref=source_port_ref,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="tentative_connection",
                    from_entry_context=EntryContext(
                        current_port_ref=source_port_ref,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=sink_port_ref,
                        incoming_edge_id=None,
                    ),
                ),
            ),
            reached_sink_port_ref=sink_port_ref,
        )

        result = V1RouteCommit()(current_state, route_plan)

        self.assertEqual("failure_snapshot", result.status)
        self.assertIsNone(result.new_state)

    def test_no_search_orchestration_behavior_is_embedded_in_commit(self) -> None:
        source_port_ref = PortRef(
            owner_ref=NodeId("source_node"),
            owner_local_key=PortId("east"),
        )
        mid_port_ref = PortRef(
            owner_ref=NodeId("mid_node"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("west"),
        )
        current_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("source_node"),
                        ports=(Port(port_ref=source_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("mid_node"),
                        ports=(Port(port_ref=mid_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("sink_node"),
                        ports=(Port(port_ref=sink_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::source_mid"),
                        port_ref_a=source_port_ref,
                        port_ref_b=mid_port_ref,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                    PortEdge(
                        edge_id=PortEdgeId("edge::mid_sink"),
                        port_ref_a=mid_port_ref,
                        port_ref_b=sink_port_ref,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                edge_ids=(PortEdgeId("edge::source_mid"), PortEdgeId("edge::mid_sink")),
            ),
        )
        invalid_direct_plan = TentativeRoutePlan(
            route_requirement_id="req::no_search",
            start_entry_context=EntryContext(
                current_port_ref=source_port_ref,
                incoming_edge_id=None,
            ),
            steps=(
                TentativeRouteStep(
                    step_kind="built_edge",
                    from_entry_context=EntryContext(
                        current_port_ref=source_port_ref,
                        incoming_edge_id=None,
                    ),
                    to_entry_context=EntryContext(
                        current_port_ref=sink_port_ref,
                        incoming_edge_id=PortEdgeId("edge::missing_direct"),
                    ),
                    via_edge_id=PortEdgeId("edge::missing_direct"),
                ),
            ),
            reached_sink_port_ref=sink_port_ref,
        )

        result = V1RouteCommit()(current_state, invalid_direct_plan)

        self.assertEqual("failure_snapshot", result.status)
        self.assertIsNone(result.new_state)


if __name__ == "__main__":
    unittest.main()
