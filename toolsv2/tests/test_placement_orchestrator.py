from __future__ import annotations

import unittest

from toolsv2.placement_orchestrator import V1PlacementOrchestrator
from toolsv2.placement_solver import PlacementSeed
from toolsv2.route_orchestrator import OrchestrationResult
from toolsv2.solver_types import (
    Junction,
    LogicalXRailId,
    LogicalYRailId,
    NodeDomain,
    NodeId,
    PortGraphIndex,
    PortGraphState,
)
from toolsv2.solver_common import RouteRequirement


class _StubRuntimeSnapshotBuilder:
    def __init__(self, built_states: tuple[PortGraphState, ...]) -> None:
        self._built_states = built_states
        self.calls: list[PlacementSeed] = []

    def __call__(self, placement_snapshot: PlacementSeed) -> PortGraphState:
        self.calls.append(placement_snapshot)
        return self._built_states[len(self.calls) - 1]


class _StubOneSnapshotRouteOrchestrator:
    def __init__(self, responses: tuple[OrchestrationResult, ...]) -> None:
        self._responses = responses
        self.calls: list[tuple[PortGraphState, tuple[RouteRequirement, ...]]] = []

    def __call__(
        self,
        initial_state: PortGraphState,
        schema_view: object,
        route_requirements: tuple[RouteRequirement, ...],
    ) -> OrchestrationResult:
        self.calls.append((initial_state, route_requirements))
        return self._responses[len(self.calls) - 1]


class PlacementOrchestratorTests(unittest.TestCase):
    def _make_seed(self, label: str) -> PlacementSeed:
        node_id = NodeId(f"{label}::node")
        junction = Junction(
            x_rail_id=LogicalXRailId(f"{label}::x"),
            y_rail_id=LogicalYRailId(f"{label}::y"),
        )
        domain = NodeDomain(
            node_id=node_id,
            junctions=frozenset({junction}),
        )
        return PlacementSeed(
            domains={node_id: domain},
            assignments={node_id: junction},
        )

    def _make_requirement(self, requirement_id: str) -> RouteRequirement:
        return RouteRequirement(
            requirement_id=requirement_id,
            source_object_ref=NodeId(f"{requirement_id}::source"),
            sink_object_ref=NodeId(f"{requirement_id}::sink"),
            requirement_kind="flow",
        )

    def test_success_on_first_placement_snapshot_stops_further_attempts(self) -> None:
        placement_snapshots = (
            self._make_seed("seed0"),
            self._make_seed("seed1"),
        )
        first_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial0"),)),
        )
        first_final_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "final0"),)),
        )
        builder = _StubRuntimeSnapshotBuilder(
            built_states=(
                first_initial_state,
                PortGraphState(graph=PortGraphIndex(attributes=(("stage", "unused"),))),
            )
        )
        route_orchestrator = _StubOneSnapshotRouteOrchestrator(
            responses=(
                OrchestrationResult(status="success", final_state=first_final_state),
            )
        )
        orchestrator = V1PlacementOrchestrator(
            runtime_snapshot_builder=builder,
            route_orchestrator=route_orchestrator,
        )

        result = orchestrator(placement_snapshots, object(), (self._make_requirement("req"),))

        self.assertEqual("success", result.status)
        self.assertEqual(0, result.placement_index)
        self.assertEqual(placement_snapshots[0], result.placement_snapshot)
        self.assertEqual(first_initial_state, result.initial_runtime_state)
        self.assertEqual(first_final_state, result.final_state)
        self.assertEqual([placement_snapshots[0]], builder.calls)
        self.assertEqual([first_initial_state], [state for state, _ in route_orchestrator.calls])

    def test_failure_on_one_placement_snapshot_proceeds_to_the_next(self) -> None:
        placement_snapshots = (
            self._make_seed("seed0"),
            self._make_seed("seed1"),
        )
        first_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial0"),)),
        )
        second_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial1"),)),
        )
        second_final_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "final1"),)),
        )
        builder = _StubRuntimeSnapshotBuilder(
            built_states=(first_initial_state, second_initial_state),
        )
        route_orchestrator = _StubOneSnapshotRouteOrchestrator(
            responses=(
                OrchestrationResult(
                    status="failure_snapshot",
                    failed_requirement_index=0,
                    failed_requirement_id="req",
                    failure_stage="router",
                    last_successful_state=first_initial_state,
                ),
                OrchestrationResult(status="success", final_state=second_final_state),
            )
        )

        result = V1PlacementOrchestrator(builder, route_orchestrator)(
            placement_snapshots,
            object(),
            (self._make_requirement("req"),),
        )

        self.assertEqual("success", result.status)
        self.assertEqual([placement_snapshots[0], placement_snapshots[1]], builder.calls)
        self.assertEqual(
            [first_initial_state, second_initial_state],
            [state for state, _ in route_orchestrator.calls],
        )

    def test_success_on_later_placement_snapshot_returns_correct_index_and_states(self) -> None:
        placement_snapshots = (
            self._make_seed("seed0"),
            self._make_seed("seed1"),
        )
        first_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial0"),)),
        )
        second_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial1"),)),
        )
        second_final_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "final1"),)),
        )
        builder = _StubRuntimeSnapshotBuilder(
            built_states=(first_initial_state, second_initial_state),
        )
        route_orchestrator = _StubOneSnapshotRouteOrchestrator(
            responses=(
                OrchestrationResult(
                    status="failure_snapshot",
                    failed_requirement_index=0,
                    failed_requirement_id="req",
                    failure_stage="router",
                    last_successful_state=first_initial_state,
                ),
                OrchestrationResult(status="success", final_state=second_final_state),
            )
        )

        result = V1PlacementOrchestrator(builder, route_orchestrator)(
            placement_snapshots,
            object(),
            (self._make_requirement("req"),),
        )

        self.assertEqual("success", result.status)
        self.assertEqual(1, result.placement_index)
        self.assertEqual(placement_snapshots[1], result.placement_snapshot)
        self.assertEqual(second_initial_state, result.initial_runtime_state)
        self.assertEqual(second_final_state, result.final_state)

    def test_exhausting_all_tried_placement_snapshots_returns_scoped_failure(self) -> None:
        placement_snapshots = (
            self._make_seed("seed0"),
            self._make_seed("seed1"),
        )
        first_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial0"),)),
        )
        second_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial1"),)),
        )
        route_orchestrator = _StubOneSnapshotRouteOrchestrator(
            responses=(
                OrchestrationResult(
                    status="failure_snapshot",
                    failed_requirement_index=0,
                    failed_requirement_id="req",
                    failure_stage="router",
                    last_successful_state=first_initial_state,
                ),
                OrchestrationResult(
                    status="failure_snapshot",
                    failed_requirement_index=0,
                    failed_requirement_id="req",
                    failure_stage="commit",
                    last_successful_state=second_initial_state,
                ),
            )
        )

        result = V1PlacementOrchestrator(
            _StubRuntimeSnapshotBuilder((first_initial_state, second_initial_state)),
            route_orchestrator,
        )(
            placement_snapshots,
            object(),
            (self._make_requirement("req"),),
        )

        self.assertEqual("failure_snapshot_set", result.status)
        self.assertEqual(2, len(result.attempts))
        self.assertEqual((0, 1), tuple(attempt.placement_index for attempt in result.attempts))
        self.assertEqual(
            placement_snapshots,
            tuple(attempt.placement_snapshot for attempt in result.attempts),
        )

    def test_no_placement_mutation_retry_reordering_or_refinement_is_embedded(self) -> None:
        placement_snapshots = (
            self._make_seed("seed0"),
            self._make_seed("seed1"),
            self._make_seed("seed2"),
        )
        first_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial0"),)),
        )
        second_initial_state = PortGraphState(
            graph=PortGraphIndex(attributes=(("stage", "initial1"),)),
        )
        builder = _StubRuntimeSnapshotBuilder(
            built_states=(
                first_initial_state,
                second_initial_state,
                PortGraphState(graph=PortGraphIndex(attributes=(("stage", "unused"),))),
            )
        )
        route_requirements = (self._make_requirement("req"),)
        route_orchestrator = _StubOneSnapshotRouteOrchestrator(
            responses=(
                OrchestrationResult(
                    status="failure_snapshot",
                    failed_requirement_index=0,
                    failed_requirement_id="req",
                    failure_stage="router",
                    last_successful_state=first_initial_state,
                ),
                OrchestrationResult(status="success", final_state=second_initial_state),
            )
        )
        original_assignments = tuple(dict(seed.assignments) for seed in placement_snapshots)

        result = V1PlacementOrchestrator(builder, route_orchestrator)(
            placement_snapshots,
            object(),
            route_requirements,
        )

        self.assertEqual("success", result.status)
        self.assertEqual(
            [placement_snapshots[0], placement_snapshots[1]],
            builder.calls,
        )
        self.assertEqual(
            [route_requirements, route_requirements],
            [called_requirements for _, called_requirements in route_orchestrator.calls],
        )
        self.assertEqual(
            original_assignments,
            tuple(dict(seed.assignments) for seed in placement_snapshots),
        )


if __name__ == "__main__":
    unittest.main()
