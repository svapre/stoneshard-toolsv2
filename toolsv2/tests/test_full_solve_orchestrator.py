from __future__ import annotations

import unittest

from toolsv2.definitions_loader import load_v1_graph_content
from toolsv2.full_solve_orchestrator import (
    CurrentGridSolver,
    FullSolveResult,
    build_v1_estimated_full_solve_orchestrator,
    build_v1_full_solve_orchestrator,
    build_v1_full_solve_orchestrator_for_layout_profile,
)
from toolsv2.graph_content import GraphContentModel, GraphContentNode, GraphContentRouteRequirement
from toolsv2.grid_expansion_policy import (
    BandExpansionStep,
    build_v1_explicit_band_expansion_policy,
)
from toolsv2.layout_estimation import (
    V1RuleBasedLayoutDemandEstimator,
    build_same_band_multi_sink_split_pattern_rule,
)
from toolsv2.layout_profiles import build_v1_vanilla_skill_tree_layout_profile
from toolsv2.layout_profiles import V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID
from toolsv2.placement_orchestrator import PlacementAttemptRecord, PlacementOrchestrationResult
from toolsv2.placement_solver import PlacementResult, PlacementSeed
from toolsv2.profile import build_minimum_active_grid
from toolsv2.route_orchestrator import OrchestrationResult
from toolsv2.solve_pipeline import CurrentGridSolveResult
from toolsv2.solver_types import (
    Junction,
    LogicalXRailId,
    LogicalYRailId,
    NodeDomain,
    NodeId,
    PortGraphState,
    PortId,
    RoutingPolicy,
)


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="full_orchestrator_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


def _seed(label: str, x_id: str, y_id: str) -> PlacementSeed:
    node_id = NodeId(f"{label}::node")
    junction = Junction(
        x_rail_id=LogicalXRailId(x_id),
        y_rail_id=LogicalYRailId(y_id),
    )
    domain = NodeDomain(node_id=node_id, junctions=frozenset({junction}))
    return PlacementSeed(
        domains={node_id: domain},
        assignments={node_id: junction},
    )


class _StubCurrentGridSolver:
    def __init__(self, responses: tuple[CurrentGridSolveResult, ...]) -> None:
        self._responses = responses
        self.calls: list[LogicalYRailId | tuple[LogicalYRailId, ...]] = []

    def __call__(self, active_grid, content) -> CurrentGridSolveResult:
        del content
        self.calls.append(tuple(rail.rail_id for rail in active_grid.y_rails))
        return self._responses[len(self.calls) - 1]


class FullSolveOrchestratorTests(unittest.TestCase):
    def test_full_orchestrator_succeeds_on_initial_grid_without_expansion(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        policy = build_v1_explicit_band_expansion_policy(initial_grid=initial_grid)
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a_source"),
                    kind="and_knot",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b_sink"),
                    kind="and_knot",
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

        result = build_v1_full_solve_orchestrator(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
            grid_expansion_policy=policy,
        )(content)

        self.assertIsInstance(result, FullSolveResult)
        self.assertEqual("success", result.status)
        self.assertEqual(initial_grid, result.initial_grid)
        self.assertEqual(1, len(result.attempts))
        self.assertEqual(initial_grid, result.final_grid)
        self.assertIsNotNone(result.final_state)
        self.assertEqual(1, len(result.final_state.objects.edges))

    def test_full_orchestrator_expands_after_placement_failure_and_succeeds(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        policy = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_mid"),),
                ),
            ),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                ),
                GraphContentNode(
                    node_id=NodeId("c"),
                    kind="skill_frame",
                ),
            ),
        )

        result = build_v1_full_solve_orchestrator(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
            grid_expansion_policy=policy,
        )(content)

        self.assertEqual("success", result.status)
        self.assertEqual(2, len(result.attempts))
        self.assertEqual(
            ("failure_on_current_grid", "success"),
            tuple(attempt.current_grid_result.placement_result.status for attempt in result.attempts),
        )
        self.assertEqual(
            ("tier_0", "dyn_mid", "tier_1"),
            tuple(str(rail.rail_id) for rail in result.final_grid.y_rails),
        )

    def test_full_orchestrator_expands_after_routing_failure_and_succeeds(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        expanded_grid = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_mid"),),
                ),
            ),
        )(initial_grid)
        assert expanded_grid is not None
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("solo"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
        )
        loaded_content = load_v1_graph_content(content)
        shared_seed = _seed("solo", "x0", "tier_0")
        routing_failure = CurrentGridSolveResult(
            status="routing_failure_on_current_grid",
            active_grid=initial_grid,
            loaded_content=loaded_content,
            placement_result=PlacementResult(status="success", seeds=(shared_seed,)),
            placement_orchestration_result=PlacementOrchestrationResult(
                status="failure_snapshot_set",
                attempts=(
                    PlacementAttemptRecord(
                        placement_index=0,
                        placement_snapshot=shared_seed,
                        initial_runtime_state=PortGraphState(),
                        route_orchestration_result=OrchestrationResult(
                            status="failure_snapshot",
                            failed_requirement_index=0,
                            failed_requirement_id="req",
                            failure_stage="router",
                            last_successful_state=PortGraphState(),
                        ),
                    ),
                ),
            ),
        )
        successful_state = PortGraphState()
        success = CurrentGridSolveResult(
            status="success",
            active_grid=expanded_grid,
            loaded_content=loaded_content,
            placement_result=PlacementResult(status="success", seeds=(shared_seed,)),
            placement_orchestration_result=PlacementOrchestrationResult(
                status="success",
                placement_index=0,
                placement_snapshot=shared_seed,
                initial_runtime_state=PortGraphState(),
                final_state=successful_state,
                route_orchestration_result=OrchestrationResult(
                    status="success",
                    final_state=successful_state,
                ),
            ),
            final_state=successful_state,
        )
        policy = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_mid"),),
                ),
            ),
        )
        solver = _StubCurrentGridSolver((routing_failure, success))

        result = build_v1_full_solve_orchestrator(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
            grid_expansion_policy=policy,
            current_grid_solver=solver,
        )(content)

        self.assertEqual("success", result.status)
        self.assertEqual(2, len(result.attempts))
        self.assertEqual(
            [
                (LogicalYRailId("tier_0"), LogicalYRailId("tier_1")),
                (LogicalYRailId("tier_0"), LogicalYRailId("dyn_mid"), LogicalYRailId("tier_1")),
            ],
            solver.calls,
        )

    def test_full_orchestrator_returns_failure_scoped_to_tried_grids(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        policy = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_mid"),),
                ),
            ),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
            ),
        )
        loaded_content = load_v1_graph_content(content)

        def _placement_failure(grid) -> CurrentGridSolveResult:
            return CurrentGridSolveResult(
                status="placement_failure_on_current_grid",
                active_grid=grid,
                loaded_content=loaded_content,
                placement_result=PlacementResult(status="failure_on_current_grid"),
            )

        second_grid = policy(initial_grid)
        assert second_grid is not None
        solver = _StubCurrentGridSolver(
            (
                _placement_failure(initial_grid),
                _placement_failure(second_grid),
            )
        )

        result = build_v1_full_solve_orchestrator(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
            grid_expansion_policy=policy,
            current_grid_solver=solver,
        )(content)

        self.assertEqual("failure_grid_set", result.status)
        self.assertEqual(2, len(result.attempts))
        self.assertIsNone(result.final_grid)
        self.assertIsNone(result.final_state)

    def test_full_orchestrator_can_be_built_from_vanilla_layout_profile(self) -> None:
        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=layout_profile.default_x_rail_ids,
            authored_tier_rail_ids=("tier_0",),
        )
        policy = build_v1_explicit_band_expansion_policy(initial_grid=initial_grid)
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("a_source"),
                    kind="and_knot",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("b_sink"),
                    kind="and_knot",
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

        result = build_v1_full_solve_orchestrator_for_layout_profile(
            layout_profile=layout_profile,
            authored_tier_rail_ids=("tier_0",),
            grid_expansion_policy=policy,
        )(content)

        self.assertEqual("success", result.status)
        self.assertEqual(
            tuple(str(rail_id) for rail_id in layout_profile.default_x_rail_ids),
            tuple(str(rail.rail_id) for rail in result.initial_grid.x_rails),
        )

    def test_estimated_full_orchestrator_starts_from_content_driven_split_grid(self) -> None:
        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=layout_profile,
            authored_tier_rail_ids=(LogicalYRailId("tier_0"), LogicalYRailId("tier_1")),
            band_layout_demand_rules=(
                build_same_band_multi_sink_split_pattern_rule(
                    split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                ),
            ),
        )
        content = GraphContentModel(
            routing_policy=_policy(),
            nodes=(
                GraphContentNode(
                    node_id=NodeId("input_a"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_0"),
                ),
                GraphContentNode(
                    node_id=NodeId("and_0"),
                    kind="and_knot",
                ),
                GraphContentNode(
                    node_id=NodeId("sink_a"),
                    kind="skill_frame",
                    authored_tier_y_rail_id=LogicalYRailId("tier_1"),
                ),
                GraphContentNode(
                    node_id=NodeId("sink_b"),
                    kind="skill_frame",
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
        estimate = estimator(content)
        successful_state = PortGraphState()
        loaded_content = load_v1_graph_content(content)
        shared_seed = _seed("solo", "x0", "tier_0")
        success = CurrentGridSolveResult(
            status="success",
            active_grid=estimate.initial_grid,
            loaded_content=loaded_content,
            placement_result=PlacementResult(status="success", seeds=(shared_seed,)),
            placement_orchestration_result=PlacementOrchestrationResult(
                status="success",
                placement_index=0,
                placement_snapshot=shared_seed,
                initial_runtime_state=PortGraphState(),
                final_state=successful_state,
                route_orchestration_result=OrchestrationResult(
                    status="success",
                    final_state=successful_state,
                ),
            ),
            final_state=successful_state,
        )
        solver = _StubCurrentGridSolver((success,))

        result = build_v1_estimated_full_solve_orchestrator(
            layout_demand_estimator=estimator,
            grid_expansion_policy_builder=lambda estimated: build_v1_explicit_band_expansion_policy(
                initial_grid=estimated.initial_grid,
            ),
            current_grid_solver=solver,
        )(content)

        self.assertEqual("success", result.status)
        self.assertEqual(
            [
                (
                    LogicalYRailId("tier_0"),
                    LogicalYRailId("dyn::tier_0::tier_1::0"),
                    LogicalYRailId("dyn::tier_0::tier_1::1"),
                    LogicalYRailId("tier_1"),
                ),
            ],
            solver.calls,
        )


if __name__ == "__main__":
    unittest.main()
