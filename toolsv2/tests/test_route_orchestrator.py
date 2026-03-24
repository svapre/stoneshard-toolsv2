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
from toolsv2.route_commit import CommitResult, V1RouteCommit
from toolsv2.route_orchestrator import V1RouteOrchestrator
from toolsv2.router import RouterResult, TentativeRoutePlan, TentativeRouteStep, V1Router
from toolsv2.solver_types import (
    EntryContext,
    Junction,
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


class _StubRouter:
    def __init__(self, responses: tuple[RouterResult, ...]) -> None:
        self._responses = responses
        self.calls: list[tuple[PortGraphState, str]] = []

    def __call__(
        self,
        state: PortGraphState,
        schema_view: object,
        route_requirement: RouteRequirement,
    ) -> RouterResult:
        self.calls.append((state, route_requirement.requirement_id))
        return self._responses[len(self.calls) - 1]


class _StubCommit:
    def __init__(self, responses: tuple[CommitResult, ...]) -> None:
        self._responses = responses
        self.calls: list[tuple[PortGraphState, str]] = []

    def __call__(
        self,
        state: PortGraphState,
        route_plan: TentativeRoutePlan,
    ) -> CommitResult:
        self.calls.append((state, route_plan.route_requirement_id))
        return self._responses[len(self.calls) - 1]


class RouteOrchestratorTests(unittest.TestCase):
    def _build_router_for_grid(self, grid) -> V1Router:
        return V1Router(
            adjacency_finder=V1JunctionAdjacencyFinder(active_grid=grid),
            geometry_build_feasibility=V1JunctionGeometryBuildFeasibility(),
            candidate_eligibility=V1CandidateEligibility(),
        )

    def _make_requirement(
        self,
        requirement_id: str,
        source_object_ref,
        sink_object_ref,
    ) -> RouteRequirement:
        return RouteRequirement(
            requirement_id=requirement_id,
            source_object_ref=source_object_ref,
            sink_object_ref=sink_object_ref,
            requirement_kind="flow",
        )

    def _make_stub_plan(self, route_requirement_id: str) -> TentativeRoutePlan:
        source_port_ref = PortRef(
            owner_ref=NodeId(f"{route_requirement_id}::source"),
            owner_local_key=PortId("east"),
        )
        sink_port_ref = PortRef(
            owner_ref=NodeId(f"{route_requirement_id}::sink"),
            owner_local_key=PortId("west"),
        )
        return TentativeRoutePlan(
            route_requirement_id=route_requirement_id,
            start_entry_context=EntryContext(
                current_port_ref=source_port_ref,
                incoming_edge_id=None,
            ),
            steps=(),
            reached_sink_port_ref=sink_port_ref,
        )

    def _make_direct_plan(
        self,
        route_requirement_id: str,
        *,
        start_port_ref: PortRef,
        step_specs: tuple[tuple[str, PortRef], ...],
        reached_sink_port_ref: PortRef,
    ) -> TentativeRoutePlan:
        steps: list[TentativeRouteStep] = []
        current_port_ref = start_port_ref
        for step_index, (step_kind, next_port_ref) in enumerate(step_specs):
            if step_kind == "built_edge":
                edge_id = PortEdgeId(f"edge::{route_requirement_id}::{step_index}")
                steps.append(
                    TentativeRouteStep(
                        step_kind="built_edge",
                        from_entry_context=EntryContext(
                            current_port_ref=current_port_ref,
                            incoming_edge_id=None,
                        ),
                        to_entry_context=EntryContext(
                            current_port_ref=next_port_ref,
                            incoming_edge_id=edge_id,
                        ),
                        via_edge_id=edge_id,
                    )
                )
            else:
                steps.append(
                    TentativeRouteStep(
                        step_kind="tentative_connection",
                        from_entry_context=EntryContext(
                            current_port_ref=current_port_ref,
                            incoming_edge_id=None,
                        ),
                        to_entry_context=EntryContext(
                            current_port_ref=next_port_ref,
                            incoming_edge_id=None,
                        ),
                    )
                )
            current_port_ref = next_port_ref

        return TentativeRoutePlan(
            route_requirement_id=route_requirement_id,
            start_entry_context=EntryContext(
                current_port_ref=start_port_ref,
                incoming_edge_id=None,
            ),
            steps=tuple(steps),
            reached_sink_port_ref=reached_sink_port_ref,
        )

    def _make_runtime_state(
        self,
        *,
        nodes: tuple[RuntimeNode, ...] = (),
        junctions: tuple = (),
        edges: tuple[PortEdge, ...] = (),
    ) -> PortGraphState:
        return PortGraphState(
            objects=RuntimeObjectSet(
                nodes=nodes,
                junctions=junctions,
                edges=edges,
            ),
            graph=PortGraphIndex(
                edge_ids=tuple(edge.edge_id for edge in edges),
            ),
        )

    def test_two_simple_requirements_route_and_commit_sequentially(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, middle_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        initial_state = PortGraphState(
            objects=RuntimeObjectSet(
                junctions=(left_junction, middle_junction, right_junction),
            ),
        )
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=left_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=middle_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=middle_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=right_junction.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirements = (
            self._make_requirement(
                "req::left_to_middle",
                left_junction.junction_id,
                middle_junction.junction_id,
            ),
            self._make_requirement(
                "req::middle_to_right",
                middle_junction.junction_id,
                right_junction.junction_id,
            ),
        )
        orchestrator = V1RouteOrchestrator(
            router=self._build_router_for_grid(grid),
            commit=V1RouteCommit(),
        )

        result = orchestrator(initial_state, schema_view, route_requirements)

        self.assertEqual("success", result.status)
        self.assertIsNotNone(result.final_state)
        self.assertEqual(2, len(result.completed))
        self.assertEqual(
            ("req::left_to_middle", "req::middle_to_right"),
            tuple(record.route_requirement_id for record in result.completed),
        )
        self.assertEqual(2, len(result.final_state.objects.edges))
        self.assertEqual((), initial_state.objects.edges)

    def test_router_failure_stops_orchestration_and_returns_last_successful_snapshot(self) -> None:
        initial_state = PortGraphState()
        first_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        route_requirements = (
            self._make_requirement("req::one", NodeId("n1"), NodeId("n2")),
            self._make_requirement("req::two", NodeId("n3"), NodeId("n4")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(status="success", route_plan=self._make_stub_plan("req::one")),
                RouterResult(status="failure_snapshot"),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
            )
        )
        orchestrator = V1RouteOrchestrator(
            router=router,
            commit=commit,
            source_flow_validator=lambda *_: True,
        )

        result = orchestrator(initial_state, object(), route_requirements)

        self.assertEqual("failure_snapshot", result.status)
        self.assertEqual(1, result.failed_requirement_index)
        self.assertEqual("req::two", result.failed_requirement_id)
        self.assertEqual("router", result.failure_stage)
        self.assertEqual(first_success_state, result.last_successful_state)
        self.assertEqual(1, len(result.completed))
        self.assertEqual("req::one", result.completed[0].route_requirement_id)

    def test_commit_failure_stops_orchestration_and_returns_last_successful_snapshot(self) -> None:
        initial_state = PortGraphState()
        first_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        route_requirements = (
            self._make_requirement("req::one", NodeId("n1"), NodeId("n2")),
            self._make_requirement("req::two", NodeId("n3"), NodeId("n4")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(status="success", route_plan=self._make_stub_plan("req::one")),
                RouterResult(status="success", route_plan=self._make_stub_plan("req::two")),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
                CommitResult(status="failure_snapshot"),
            )
        )
        orchestrator = V1RouteOrchestrator(
            router=router,
            commit=commit,
            source_flow_validator=lambda *_: True,
        )

        result = orchestrator(initial_state, object(), route_requirements)

        self.assertEqual("failure_snapshot", result.status)
        self.assertEqual(1, result.failed_requirement_index)
        self.assertEqual("req::two", result.failed_requirement_id)
        self.assertEqual("commit", result.failure_stage)
        self.assertEqual(first_success_state, result.last_successful_state)
        self.assertEqual(1, len(result.completed))
        self.assertEqual("req::one", result.completed[0].route_requirement_id)

    def test_completed_prefix_records_are_preserved_on_failure(self) -> None:
        initial_state = PortGraphState()
        first_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        route_requirements = (
            self._make_requirement("req::one", NodeId("n1"), NodeId("n2")),
            self._make_requirement("req::two", NodeId("n3"), NodeId("n4")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(status="success", route_plan=self._make_stub_plan("req::one")),
                RouterResult(status="failure_snapshot"),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
            )
        )

        result = V1RouteOrchestrator(
            router=router,
            commit=commit,
            source_flow_validator=lambda *_: True,
        )(
            initial_state,
            object(),
            route_requirements,
        )

        self.assertEqual(
            ("req::one",),
            tuple(record.route_requirement_id for record in result.completed),
        )

    def test_orchestrator_does_not_mutate_initial_snapshot_in_place(self) -> None:
        initial_state = PortGraphState()
        updated_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        route_requirements = (
            self._make_requirement("req::one", NodeId("n1"), NodeId("n2")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(status="success", route_plan=self._make_stub_plan("req::one")),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=updated_state),
            )
        )
        orchestrator = V1RouteOrchestrator(
            router=router,
            commit=commit,
            source_flow_validator=lambda *_: True,
        )

        result = orchestrator(initial_state, object(), route_requirements)

        self.assertEqual("success", result.status)
        self.assertEqual(PortGraphState(), initial_state)
        self.assertEqual((), initial_state.objects.edges)
        self.assertEqual(updated_state, result.final_state)

    def test_source_grouping_preserves_first_source_appearance_and_intra_source_order(self) -> None:
        initial_state = PortGraphState()
        first_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        second_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "2"),)),
        )
        third_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "3"),)),
        )
        route_requirements = (
            self._make_requirement("req::source_a__first", NodeId("source_a"), NodeId("sink_1")),
            self._make_requirement("req::source_b__only", NodeId("source_b"), NodeId("sink_2")),
            self._make_requirement("req::source_a__second", NodeId("source_a"), NodeId("sink_3")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(
                    status="success",
                    route_plan=self._make_stub_plan("req::source_a__first"),
                ),
                RouterResult(
                    status="success",
                    route_plan=self._make_stub_plan("req::source_a__second"),
                ),
                RouterResult(
                    status="success",
                    route_plan=self._make_stub_plan("req::source_b__only"),
                ),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
                CommitResult(status="success", new_state=second_success_state),
                CommitResult(status="success", new_state=third_success_state),
            )
        )

        result = V1RouteOrchestrator(
            router=router,
            commit=commit,
            source_flow_validator=lambda *_: True,
        )(
            initial_state,
            object(),
            route_requirements,
        )

        self.assertEqual("success", result.status)
        self.assertEqual(
            [
                "req::source_a__first",
                "req::source_a__second",
                "req::source_b__only",
            ],
            [requirement_id for _, requirement_id in router.calls],
        )
        self.assertEqual(
            [
                "req::source_a__first",
                "req::source_a__second",
                "req::source_b__only",
            ],
            [route_requirement_id for _, route_requirement_id in commit.calls],
        )

    def test_same_source_additive_fanout_is_allowed_by_source_tree_validation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        junction_b, junction_c = build_runtime_junctions_for_active_grid(grid)
        source_port_ref = PortRef(
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
        source_node = RuntimeNode(
            node_id=NodeId("node_a"),
            ports=(Port(port_ref=source_port_ref),),
        )
        initial_state = self._make_runtime_state(
            nodes=(source_node,),
            junctions=(junction_b, junction_c),
        )
        first_success_state = self._make_runtime_state(
            nodes=(source_node,),
            junctions=(junction_b, junction_c),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::a_to_b"),
                    port_ref_a=source_port_ref,
                    port_ref_b=junction_b_west,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
            ),
        )
        second_success_state = self._make_runtime_state(
            nodes=(source_node,),
            junctions=(junction_b, junction_c),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::a_to_b"),
                    port_ref_a=source_port_ref,
                    port_ref_b=junction_b_west,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
                PortEdge(
                    edge_id=PortEdgeId("edge::b_to_c"),
                    port_ref_a=junction_b_west,
                    port_ref_b=junction_c_west,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
            ),
        )
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_a"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=junction_b.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=junction_c.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirements = (
            self._make_requirement("req::a_to_b", NodeId("node_a"), junction_b.junction_id),
            self._make_requirement("req::a_to_c", NodeId("node_a"), junction_c.junction_id),
        )
        router = _StubRouter(
            responses=(
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::a_to_b",
                        start_port_ref=source_port_ref,
                        step_specs=(("tentative_connection", junction_b_west),),
                        reached_sink_port_ref=junction_b_west,
                    ),
                ),
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::a_to_c",
                        start_port_ref=source_port_ref,
                        step_specs=(
                            ("built_edge", junction_b_west),
                            ("tentative_connection", junction_c_west),
                        ),
                        reached_sink_port_ref=junction_c_west,
                    ),
                ),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
                CommitResult(status="success", new_state=second_success_state),
            )
        )

        result = V1RouteOrchestrator(router=router, commit=commit)(
            initial_state,
            schema_view,
            route_requirements,
        )

        self.assertEqual("success", result.status)
        self.assertEqual(second_success_state, result.final_state)

    def test_same_source_can_reuse_existing_suffix_after_new_prefix(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3"),
            authored_tier_rail_ids=("tier_0",),
        )
        junction_a, junction_b, junction_c, junction_d = build_runtime_junctions_for_active_grid(grid)
        source_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        first_sink_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        second_sink_port_ref = PortRef(
            owner_ref=NodeId("node_c"),
            owner_local_key=PortId("west"),
        )
        source_node = RuntimeNode(
            node_id=NodeId("node_a"),
            ports=(Port(port_ref=source_port_ref),),
        )
        first_sink_node = RuntimeNode(
            node_id=NodeId("node_b"),
            ports=(Port(port_ref=first_sink_port_ref),),
        )
        second_sink_node = RuntimeNode(
            node_id=NodeId("node_c"),
            ports=(Port(port_ref=second_sink_port_ref),),
        )
        initial_state = self._make_runtime_state(
            nodes=(source_node, first_sink_node, second_sink_node),
            junctions=(junction_a, junction_b, junction_c, junction_d),
        )
        first_success_state = self._make_runtime_state(
            nodes=(source_node, first_sink_node, second_sink_node),
            junctions=(junction_a, junction_b, junction_c, junction_d),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::source_to_jb"),
                    port_ref_a=source_port_ref,
                    port_ref_b=PortRef(
                        owner_ref=junction_b.junction_id,
                        owner_local_key=PortId("west"),
                    ),
                    scope="external",
                    traversal_mode="bidirectional",
                ),
                PortEdge(
                    edge_id=PortEdgeId("edge::jb_to_jc"),
                    port_ref_a=PortRef(
                        owner_ref=junction_b.junction_id,
                        owner_local_key=PortId("east"),
                    ),
                    port_ref_b=PortRef(
                        owner_ref=junction_c.junction_id,
                        owner_local_key=PortId("west"),
                    ),
                    scope="external",
                    traversal_mode="bidirectional",
                ),
                PortEdge(
                    edge_id=PortEdgeId("edge::jc_to_first_sink"),
                    port_ref_a=PortRef(
                        owner_ref=junction_c.junction_id,
                        owner_local_key=PortId("east"),
                    ),
                    port_ref_b=first_sink_port_ref,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
            ),
        )
        second_success_state = self._make_runtime_state(
            nodes=(source_node, first_sink_node, second_sink_node),
            junctions=(junction_a, junction_b, junction_c, junction_d),
            edges=first_success_state.objects.edges
            + (
                PortEdge(
                    edge_id=PortEdgeId("edge::source_to_jd"),
                    port_ref_a=source_port_ref,
                    port_ref_b=PortRef(
                        owner_ref=junction_d.junction_id,
                        owner_local_key=PortId("west"),
                    ),
                    scope="external",
                    traversal_mode="bidirectional",
                ),
                PortEdge(
                    edge_id=PortEdgeId("edge::jd_to_jb"),
                    port_ref_a=PortRef(
                        owner_ref=junction_d.junction_id,
                        owner_local_key=PortId("east"),
                    ),
                    port_ref_b=PortRef(
                        owner_ref=junction_b.junction_id,
                        owner_local_key=PortId("east"),
                    ),
                    scope="external",
                    traversal_mode="bidirectional",
                ),
                PortEdge(
                    edge_id=PortEdgeId("edge::jc_to_second_sink"),
                    port_ref_a=PortRef(
                        owner_ref=junction_c.junction_id,
                        owner_local_key=PortId("east"),
                    ),
                    port_ref_b=second_sink_port_ref,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
            ),
        )
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_a"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_b"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_c"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirements = (
            self._make_requirement("req::a_to_b", NodeId("node_a"), NodeId("node_b")),
            self._make_requirement("req::a_to_c", NodeId("node_a"), NodeId("node_c")),
        )
        router = _StubRouter(
            responses=(
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::a_to_b",
                        start_port_ref=source_port_ref,
                        step_specs=(
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_b.junction_id,
                                    owner_local_key=PortId("west"),
                                ),
                            ),
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_b.junction_id,
                                    owner_local_key=PortId("east"),
                                ),
                            ),
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_c.junction_id,
                                    owner_local_key=PortId("west"),
                                ),
                            ),
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_c.junction_id,
                                    owner_local_key=PortId("east"),
                                ),
                            ),
                            (
                                "tentative_connection",
                                first_sink_port_ref,
                            ),
                        ),
                        reached_sink_port_ref=first_sink_port_ref,
                    ),
                ),
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::a_to_c",
                        start_port_ref=source_port_ref,
                        step_specs=(
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_d.junction_id,
                                    owner_local_key=PortId("west"),
                                ),
                            ),
                            (
                                "tentative_connection",
                                PortRef(
                                    owner_ref=junction_b.junction_id,
                                    owner_local_key=PortId("east"),
                                ),
                            ),
                            (
                                "built_edge",
                                PortRef(
                                    owner_ref=junction_c.junction_id,
                                    owner_local_key=PortId("west"),
                                ),
                            ),
                            (
                                "built_edge",
                                PortRef(
                                    owner_ref=junction_c.junction_id,
                                    owner_local_key=PortId("east"),
                                ),
                            ),
                            ("tentative_connection", second_sink_port_ref),
                        ),
                        reached_sink_port_ref=second_sink_port_ref,
                    ),
                ),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
                CommitResult(status="success", new_state=second_success_state),
            )
        )

        result = V1RouteOrchestrator(router=router, commit=commit)(
            initial_state,
            schema_view,
            route_requirements,
        )

        self.assertEqual("success", result.status)
        self.assertEqual(second_success_state, result.final_state)

    def test_reaching_foreign_non_sink_node_port_is_rejected_by_orchestrator(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2"),
            authored_tier_rail_ids=("tier_0",),
        )
        junction_b, junction_c, junction_d = build_runtime_junctions_for_active_grid(grid)
        node_a_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        node_c_port_ref = PortRef(
            owner_ref=NodeId("node_c"),
            owner_local_key=PortId("east"),
        )
        junction_b_west = PortRef(
            owner_ref=junction_b.junction_id,
            owner_local_key=PortId("west"),
        )
        junction_c_east = PortRef(
            owner_ref=junction_c.junction_id,
            owner_local_key=PortId("east"),
        )
        junction_d_west = PortRef(
            owner_ref=junction_d.junction_id,
            owner_local_key=PortId("west"),
        )
        node_a = RuntimeNode(
            node_id=NodeId("node_a"),
            ports=(Port(port_ref=node_a_port_ref),),
        )
        node_c = RuntimeNode(
            node_id=NodeId("node_c"),
            ports=(Port(port_ref=node_c_port_ref),),
        )
        initial_state = self._make_runtime_state(
            nodes=(node_a, node_c),
            junctions=(junction_b, junction_c, junction_d),
        )
        first_success_state = self._make_runtime_state(
            nodes=(node_a, node_c),
            junctions=(junction_b, junction_c, junction_d),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::a_to_b"),
                    port_ref_a=node_a_port_ref,
                    port_ref_b=junction_b_west,
                    scope="external",
                    traversal_mode="bidirectional",
                ),
            ),
        )
        schema_view = StaticRouteRequirementSchemaView(
            source_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_a"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=NodeId("node_c"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("east"),),
                ),
            ),
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=junction_b.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
                RouteRequirementPortAllowance(
                    object_ref=junction_d.junction_id,
                    requirement_kind="flow",
                    port_local_keys=(PortId("west"),),
                ),
            ),
        )
        route_requirements = (
            self._make_requirement("req::a_to_b", NodeId("node_a"), junction_b.junction_id),
            self._make_requirement("req::c_to_d", NodeId("node_c"), junction_d.junction_id),
        )
        router = _StubRouter(
            responses=(
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::a_to_b",
                        start_port_ref=node_a_port_ref,
                        step_specs=(("tentative_connection", junction_b_west),),
                        reached_sink_port_ref=junction_b_west,
                    ),
                ),
                RouterResult(
                    status="success",
                    route_plan=self._make_direct_plan(
                        "req::c_to_d",
                        start_port_ref=node_c_port_ref,
                        step_specs=(
                            ("tentative_connection", junction_b_west),
                            ("built_edge", node_a_port_ref),
                            ("tentative_connection", junction_d_west),
                        ),
                        reached_sink_port_ref=junction_d_west,
                    ),
                ),
            )
        )
        commit = _StubCommit(
            responses=(
                CommitResult(status="success", new_state=first_success_state),
                CommitResult(status="success", new_state=first_success_state),
            )
        )

        result = V1RouteOrchestrator(router=router, commit=commit)(
            initial_state,
            schema_view,
            route_requirements,
        )

        self.assertEqual("failure_snapshot", result.status)
        self.assertEqual(1, result.failed_requirement_index)
        self.assertEqual("req::c_to_d", result.failed_requirement_id)
        self.assertEqual("commit", result.failure_stage)
        self.assertEqual(first_success_state, result.last_successful_state)


if __name__ == "__main__":
    unittest.main()
