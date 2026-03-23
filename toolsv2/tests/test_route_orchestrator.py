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
from toolsv2.router import RouterResult, TentativeRoutePlan, V1Router
from toolsv2.solver_types import (
    EntryContext,
    PortGraphIndex,
    PortGraphState,
    PortId,
    PortRef,
    RouteRequirement,
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
        orchestrator = V1RouteOrchestrator(router=router, commit=commit)

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
        orchestrator = V1RouteOrchestrator(router=router, commit=commit)

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

        result = V1RouteOrchestrator(router=router, commit=commit)(
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
        orchestrator = V1RouteOrchestrator(router=router, commit=commit)

        result = orchestrator(initial_state, object(), route_requirements)

        self.assertEqual("success", result.status)
        self.assertEqual(PortGraphState(), initial_state)
        self.assertEqual((), initial_state.objects.edges)
        self.assertEqual(updated_state, result.final_state)

    def test_no_reordering_retry_or_backtracking_behavior_is_embedded(self) -> None:
        initial_state = PortGraphState()
        first_success_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "1"),)),
        )
        route_requirements = (
            self._make_requirement("req::one", NodeId("n1"), NodeId("n2")),
            self._make_requirement("req::two", NodeId("n3"), NodeId("n4")),
            self._make_requirement("req::three", NodeId("n5"), NodeId("n6")),
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

        result = V1RouteOrchestrator(router=router, commit=commit)(
            initial_state,
            object(),
            route_requirements,
        )

        self.assertEqual("failure_snapshot", result.status)
        self.assertEqual(
            ["req::one", "req::two"],
            [requirement_id for _, requirement_id in router.calls],
        )
        self.assertEqual(
            ["req::one"],
            [route_requirement_id for _, route_requirement_id in commit.calls],
        )


if __name__ == "__main__":
    unittest.main()
