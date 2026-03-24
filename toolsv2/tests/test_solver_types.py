from __future__ import annotations

from dataclasses import replace
import inspect
import unittest
from fractions import Fraction

from toolsv2.adjacency import (
    CROSS_OBJECT_BOUNDARY_RELATION_KIND,
    LOCAL_SAME_OBJECT_RELATION_KIND,
    V1JunctionAdjacencyFinder,
)
from toolsv2.entry_queries import (
    directly_reachable_next_entry_contexts,
    is_entry_context_usable,
)
from toolsv2.eligibility import (
    StaticRouteRequirementSchemaView,
    RouteRequirementPortAllowance,
    V1CandidateEligibility,
)
from toolsv2.geometry import V1JunctionGeometryBuildFeasibility
from toolsv2 import solver_common, solver_runtime, solver_schema, solver_types
from toolsv2.profile import build_minimum_active_grid
from toolsv2.solver_types import (
    ActiveGridState,
    AdjacencyFinder,
    BandId,
    build_runtime_junctions_for_active_grid,
    can_port_ref_accept_new_attachment,
    CandidateEligibility,
    EntryContext,
    direct_attachment_count,
    Junction,
    FrontierContext,
    GeometryBuildFeasibility,
    LogicalXRail,
    LogicalXRailId,
    LogicalYRail,
    LogicalYRailId,
    NeighborRelation,
    NodeDefinition,
    NodeDomain,
    NodeId,
    is_edge_id_usable,
    is_object_ref_active,
    is_port_ref_usable,
    Port,
    PortDefinition,
    PortEdge,
    PortEdgeId,
    PortGraphIndex,
    PortGraphState,
    PortId,
    PortRef,
    RenderProfileKey,
    RenderProfileRef,
    RouteRequirement,
    RouteRequirementSchemaView,
    RuntimeJunction,
    RuntimeNode,
    RuntimeObjectSet,
    YRailBandState,
)
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    ConnectionFamilyKey,
    DEFAULT_AND_KNOT_PROFILE_KEY,
    DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
    InternalTransitionSpec,
    LocalFootprint,
    PortGeometrySpec,
    RenderStyleProfile,
    StaticVisualProfileCatalog,
    build_v1_core_visual_profile_catalog,
)


class SolverTypesTests(unittest.TestCase):
    def test_solver_types_reexports_schema_and_runtime_modules(self) -> None:
        self.assertIs(solver_types.NodeDefinition, solver_schema.NodeDefinition)
        self.assertIs(solver_types.PortDefinition, solver_schema.PortDefinition)
        self.assertIs(solver_types.RuntimeNode, solver_runtime.RuntimeNode)
        self.assertIs(solver_types.PortGraphState, solver_runtime.PortGraphState)
        self.assertIs(solver_types.PortRef, solver_common.PortRef)
        self.assertIs(solver_types.is_edge_id_usable, solver_runtime.is_edge_id_usable)
        self.assertIs(
            solver_types.build_runtime_junctions_for_active_grid,
            solver_runtime.build_runtime_junctions_for_active_grid,
        )
        self.assertIs(solver_types.FrontierContext, solver_common.FrontierContext)
        self.assertIs(solver_types.EntryContext, solver_common.EntryContext)
        self.assertIs(solver_types.NeighborRelation, solver_common.NeighborRelation)
        self.assertIs(solver_types.RouteRequirement, solver_common.RouteRequirement)
        self.assertIs(
            solver_types.RouteRequirementSchemaView,
            solver_common.RouteRequirementSchemaView,
        )

    def test_frontier_context_record_is_minimal(self) -> None:
        context = FrontierContext(
            current_object_ref=NodeId("node_a"),
            current_port_ref=PortRef(
                owner_ref=NodeId("node_a"),
                owner_local_key=PortId("east"),
            ),
        )

        self.assertEqual(
            {"current_object_ref", "current_port_ref"},
            set(context.__dataclass_fields__),
        )
        self.assertEqual(NodeId("node_a"), context.current_object_ref)

    def test_entry_context_record_supports_start_context(self) -> None:
        context = EntryContext(
            current_port_ref=PortRef(
                owner_ref=NodeId("node_a"),
                owner_local_key=PortId("east"),
            ),
            incoming_edge_id=None,
        )

        self.assertEqual(
            {"current_port_ref", "incoming_edge_id"},
            set(context.__dataclass_fields__),
        )
        self.assertIsNone(context.incoming_edge_id)

    def test_neighbor_relation_record_is_minimal(self) -> None:
        relation = NeighborRelation(
            from_object_ref=NodeId("node_a"),
            to_object_ref=Junction(
                x_rail_id=LogicalXRailId("x0"),
                y_rail_id=LogicalYRailId("tier_0"),
            ),
            relation_kind="adjacent",
            approach_direction="east",
        )

        self.assertEqual(
            {
                "from_object_ref",
                "to_object_ref",
                "relation_kind",
                "approach_direction",
            },
            set(relation.__dataclass_fields__),
        )
        self.assertEqual("adjacent", relation.relation_kind)
        self.assertEqual("east", relation.approach_direction)

    def test_routing_layer_contracts_are_thin_callables(self) -> None:
        adjacency_signature = inspect.signature(AdjacencyFinder.__call__)
        geometry_signature = inspect.signature(GeometryBuildFeasibility.__call__)
        eligibility_signature = inspect.signature(CandidateEligibility.__call__)

        self.assertEqual(
            ["self", "runtime_objects", "frontier_context"],
            list(adjacency_signature.parameters),
        )
        self.assertEqual(
            ["self", "runtime_objects", "frontier_context", "neighbor_relation"],
            list(geometry_signature.parameters),
        )
        self.assertEqual(
            [
                "self",
                "runtime_objects",
                "schema_view",
                "frontier_context",
                "neighbor_relation",
                "route_requirement",
                "candidate_port_ref",
            ],
            list(eligibility_signature.parameters),
        )

    def test_active_plain_junction_returns_same_object_local_neighbor_relation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]
        runtime_objects = RuntimeObjectSet(junctions=(runtime_junction,))
        finder = V1JunctionAdjacencyFinder(active_grid=grid)

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=runtime_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=runtime_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
        )

        self.assertIn(
            NeighborRelation(
                from_object_ref=runtime_junction.junction_id,
                to_object_ref=runtime_junction.junction_id,
                relation_kind=LOCAL_SAME_OBJECT_RELATION_KIND,
                approach_direction="west",
            ),
            relations,
        )

    def test_adjacent_junction_context_returns_expected_cross_object_neighbor_relation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junctions = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(junctions=runtime_junctions)
        left_junction = next(
            junction
            for junction in runtime_junctions
            if junction.junction_id.x_rail_id == LogicalXRailId("x0")
        )
        right_junction = next(
            junction
            for junction in runtime_junctions
            if junction.junction_id.x_rail_id == LogicalXRailId("x1")
        )
        finder = V1JunctionAdjacencyFinder(active_grid=grid)

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
        )

        self.assertIn(
            NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            relations,
        )

    def test_inactive_junction_does_not_produce_local_adjacency_relations(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junction = replace(
            build_runtime_junctions_for_active_grid(grid)[0],
            is_active=False,
        )
        runtime_objects = RuntimeObjectSet(junctions=(runtime_junction,))
        finder = V1JunctionAdjacencyFinder(active_grid=grid)

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=runtime_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=runtime_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
        )

        self.assertEqual((), relations)

    def test_non_adjacent_junctions_are_not_returned_as_cross_object_neighbors(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2"),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junctions = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(junctions=runtime_junctions)
        left_junction = next(
            junction
            for junction in runtime_junctions
            if junction.junction_id.x_rail_id == LogicalXRailId("x0")
        )
        far_right_junction = next(
            junction
            for junction in runtime_junctions
            if junction.junction_id.x_rail_id == LogicalXRailId("x2")
        )
        finder = V1JunctionAdjacencyFinder(active_grid=grid)

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
        )

        self.assertNotIn(
            NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=far_right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            relations,
        )

    def test_adjacency_finder_does_not_embed_port_feasibility_or_eligibility(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        right_west_port = next(
            port
            for port in right_junction.ports
            if port.port_ref.owner_local_key == PortId("west")
        )
        right_junction_with_inactive_boundary_port = replace(
            right_junction,
            ports=tuple(
                replace(port, is_active=False) if port == right_west_port else port
                for port in right_junction.ports
            ),
        )
        runtime_objects = RuntimeObjectSet(
            junctions=(left_junction, right_junction_with_inactive_boundary_port),
        )
        finder = V1JunctionAdjacencyFinder(active_grid=grid)

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
        )

        self.assertIn(
            NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            relations,
        )

    def test_node_frontier_returns_cross_object_neighbor_relation_to_adjacent_junction(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        source_node = RuntimeNode(
            node_id=NodeId("source_node"),
            current_junction_id=left_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(source_node,),
            junctions=(
                replace(left_junction, occupying_node_id=source_node.node_id, is_active=False),
                right_junction,
            ),
        )
        finder = V1JunctionAdjacencyFinder(
            active_grid=grid,
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=source_node.node_id,
                current_port_ref=PortRef(
                    owner_ref=source_node.node_id,
                    owner_local_key=PortId("right"),
                ),
            ),
        )

        self.assertEqual(
            (
                NeighborRelation(
                    from_object_ref=source_node.node_id,
                    to_object_ref=right_junction.junction_id,
                    relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                    approach_direction="east",
                ),
            ),
            relations,
        )

    def test_node_frontier_returns_adjacent_occupied_node_neighbor_relation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        source_node = RuntimeNode(
            node_id=NodeId("source_node"),
            current_junction_id=left_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            current_junction_id=right_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(source_node, sink_node),
            junctions=(
                replace(left_junction, occupying_node_id=source_node.node_id, is_active=False),
                replace(right_junction, occupying_node_id=sink_node.node_id, is_active=False),
            ),
        )
        finder = V1JunctionAdjacencyFinder(
            active_grid=grid,
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=source_node.node_id,
                current_port_ref=PortRef(
                    owner_ref=source_node.node_id,
                    owner_local_key=PortId("right"),
                ),
            ),
        )

        self.assertEqual(
            (
                NeighborRelation(
                    from_object_ref=source_node.node_id,
                    to_object_ref=sink_node.node_id,
                    relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                    approach_direction="east",
                ),
            ),
            relations,
        )

    def test_junction_frontier_returns_adjacent_node_neighbor_relation(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            current_junction_id=right_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(sink_node,),
            junctions=(
                left_junction,
                replace(right_junction, occupying_node_id=sink_node.node_id, is_active=False),
            ),
        )
        finder = V1JunctionAdjacencyFinder(
            active_grid=grid,
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        relations = finder(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
        )

        self.assertIn(
            NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=sink_node.node_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            relations,
        )

    def test_same_object_local_geometry_returns_distinct_ports_on_same_junction(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]
        runtime_objects = RuntimeObjectSet(junctions=(runtime_junction,))
        geometry = V1JunctionGeometryBuildFeasibility()

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=runtime_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=runtime_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=runtime_junction.junction_id,
                to_object_ref=runtime_junction.junction_id,
                relation_kind=LOCAL_SAME_OBJECT_RELATION_KIND,
                approach_direction="west",
            ),
        )

        self.assertEqual(
            {
                PortRef(owner_ref=runtime_junction.junction_id, owner_local_key=PortId("north")),
                PortRef(owner_ref=runtime_junction.junction_id, owner_local_key=PortId("south")),
                PortRef(owner_ref=runtime_junction.junction_id, owner_local_key=PortId("east")),
            },
            set(candidates),
        )

    def test_cross_object_boundary_geometry_returns_single_boundary_port(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(junctions=(left_junction, right_junction))
        geometry = V1JunctionGeometryBuildFeasibility()

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual(
            (
                PortRef(
                    owner_ref=right_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
            candidates,
        )

    def test_node_to_junction_geometry_returns_opposite_boundary_port(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        source_node = RuntimeNode(
            node_id=NodeId("source_node"),
            current_junction_id=left_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(source_node,),
            junctions=(
                replace(left_junction, occupying_node_id=source_node.node_id, is_active=False),
                right_junction,
            ),
        )
        geometry = V1JunctionGeometryBuildFeasibility(
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=source_node.node_id,
                current_port_ref=PortRef(
                    owner_ref=source_node.node_id,
                    owner_local_key=PortId("right"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=source_node.node_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual(
            (
                PortRef(owner_ref=right_junction.junction_id, owner_local_key=PortId("west")),
            ),
            candidates,
        )

    def test_junction_to_node_geometry_returns_opposite_boundary_node_port(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            current_junction_id=right_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(sink_node,),
            junctions=(
                left_junction,
                replace(right_junction, occupying_node_id=sink_node.node_id, is_active=False),
            ),
        )
        geometry = V1JunctionGeometryBuildFeasibility(
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=sink_node.node_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual(
            (
                PortRef(owner_ref=sink_node.node_id, owner_local_key=PortId("left")),
            ),
            candidates,
        )

    def test_node_to_node_geometry_returns_opposite_boundary_node_port(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        source_node = RuntimeNode(
            node_id=NodeId("source_node"),
            current_junction_id=left_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("source_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            current_junction_id=right_junction.junction_id,
            ports=(
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("top"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("left"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("right"))),
                Port(port_ref=PortRef(owner_ref=NodeId("sink_node"), owner_local_key=PortId("bottom"))),
            ),
            render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(source_node, sink_node),
            junctions=(
                replace(left_junction, occupying_node_id=source_node.node_id, is_active=False),
                replace(right_junction, occupying_node_id=sink_node.node_id, is_active=False),
            ),
        )
        geometry = V1JunctionGeometryBuildFeasibility(
            visual_profile_catalog=build_v1_core_visual_profile_catalog(
                skill_frame_top_port_id=PortId("top"),
                skill_frame_bottom_port_id=PortId("bottom"),
                and_knot_top_port_id=PortId("top"),
                and_knot_left_port_id=PortId("left"),
                and_knot_right_port_id=PortId("right"),
                and_knot_bottom_port_id=PortId("bottom"),
            ),
        )

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=source_node.node_id,
                current_port_ref=PortRef(
                    owner_ref=source_node.node_id,
                    owner_local_key=PortId("right"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=source_node.node_id,
                to_object_ref=sink_node.node_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual(
            (
                PortRef(owner_ref=sink_node.node_id, owner_local_key=PortId("left")),
            ),
            candidates,
        )

    def test_cross_object_boundary_geometry_does_not_return_non_boundary_ports(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(junctions=(left_junction, right_junction))
        geometry = V1JunctionGeometryBuildFeasibility()

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertNotIn(
            PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("north"),
            ),
            candidates,
        )
        self.assertNotIn(
            PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("east"),
            ),
            candidates,
        )

    def test_geometry_returns_no_candidates_for_inactive_target_or_unusable_context(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        inactive_right_junction = replace(right_junction, is_active=False)
        runtime_objects_with_inactive_target = RuntimeObjectSet(
            junctions=(left_junction, inactive_right_junction),
        )
        geometry = V1JunctionGeometryBuildFeasibility()

        no_target_candidates = geometry(
            runtime_objects=runtime_objects_with_inactive_target,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        inactive_east_port = next(
            port
            for port in left_junction.ports
            if port.port_ref.owner_local_key == PortId("east")
        )
        unusable_left_junction = replace(
            left_junction,
            ports=tuple(
                replace(port, is_active=False) if port == inactive_east_port else port
                for port in left_junction.ports
            ),
        )
        runtime_objects_with_unusable_context = RuntimeObjectSet(
            junctions=(unusable_left_junction, right_junction),
        )
        no_context_candidates = geometry(
            runtime_objects=runtime_objects_with_unusable_context,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual((), no_target_candidates)
        self.assertEqual((), no_context_candidates)

    def test_geometry_does_not_embed_logical_eligibility_or_route_semantics(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        right_west_port = next(
            port
            for port in right_junction.ports
            if port.port_ref.owner_local_key == PortId("west")
        )
        right_junction_with_unusable_boundary_port = replace(
            right_junction,
            ports=tuple(
                replace(port, is_active=False) if port == right_west_port else port
                for port in right_junction.ports
            ),
        )
        runtime_objects = RuntimeObjectSet(
            junctions=(left_junction, right_junction_with_unusable_boundary_port),
        )
        geometry = V1JunctionGeometryBuildFeasibility()

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual(
            (
                PortRef(
                    owner_ref=right_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
            candidates,
        )

    def test_same_object_local_geometry_uses_profile_internal_transitions(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        runtime_junction = replace(
            build_runtime_junctions_for_active_grid(grid)[0],
            render_profile=RenderProfileRef(
                profile_key=RenderProfileKey("junction/custom_local"),
            ),
        )
        runtime_objects = RuntimeObjectSet(junctions=(runtime_junction,))
        geometry = V1JunctionGeometryBuildFeasibility(
            visual_profile_catalog=StaticVisualProfileCatalog(
                build_geometry_profiles=(
                    BuildGeometryProfile(
                        profile_key=RenderProfileKey("junction/custom_local"),
                        footprint=LocalFootprint(width=5, height=5),
                        ports=(
                            PortGeometrySpec(
                                port_id=PortId("north"),
                                offset_x=2,
                                offset_y=0,
                                attach_direction="north",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("south"),
                                offset_x=2,
                                offset_y=4,
                                attach_direction="south",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("west"),
                                offset_x=0,
                                offset_y=2,
                                attach_direction="west",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("east"),
                                offset_x=4,
                                offset_y=2,
                                attach_direction="east",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                        ),
                        internal_transitions=(
                            InternalTransitionSpec(
                                from_port_id=PortId("west"),
                                to_port_id=PortId("east"),
                                connection_family_key=ConnectionFamilyKey("road_basic"),
                            ),
                        ),
                    ),
                ),
                render_style_profiles=(
                    RenderStyleProfile(
                        profile_key=RenderProfileKey("junction/custom_local"),
                    ),
                ),
            ),
        )

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=runtime_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=runtime_junction.junction_id,
                    owner_local_key=PortId("west"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=runtime_junction.junction_id,
                to_object_ref=runtime_junction.junction_id,
                relation_kind=LOCAL_SAME_OBJECT_RELATION_KIND,
                approach_direction="west",
            ),
        )

        self.assertEqual(
            (
                PortRef(
                    owner_ref=runtime_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            candidates,
        )

    def test_cross_object_boundary_geometry_requires_shared_profile_connection_family(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        left_junction = replace(
            left_junction,
            render_profile=RenderProfileRef(
                profile_key=RenderProfileKey("junction/left_custom"),
            ),
        )
        right_junction = replace(
            right_junction,
            render_profile=RenderProfileRef(
                profile_key=RenderProfileKey("junction/right_custom"),
            ),
        )
        runtime_objects = RuntimeObjectSet(junctions=(left_junction, right_junction))
        geometry = V1JunctionGeometryBuildFeasibility(
            visual_profile_catalog=StaticVisualProfileCatalog(
                build_geometry_profiles=(
                    BuildGeometryProfile(
                        profile_key=RenderProfileKey("junction/left_custom"),
                        footprint=LocalFootprint(width=5, height=5),
                        ports=(
                            PortGeometrySpec(
                                port_id=PortId("north"),
                                offset_x=2,
                                offset_y=0,
                                attach_direction="north",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("south"),
                                offset_x=2,
                                offset_y=4,
                                attach_direction="south",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("west"),
                                offset_x=0,
                                offset_y=2,
                                attach_direction="west",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("east"),
                                offset_x=4,
                                offset_y=2,
                                attach_direction="east",
                                connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                            ),
                        ),
                    ),
                    BuildGeometryProfile(
                        profile_key=RenderProfileKey("junction/right_custom"),
                        footprint=LocalFootprint(width=5, height=5),
                        ports=(
                            PortGeometrySpec(
                                port_id=PortId("north"),
                                offset_x=2,
                                offset_y=0,
                                attach_direction="north",
                                connection_family_keys=(ConnectionFamilyKey("road_other"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("south"),
                                offset_x=2,
                                offset_y=4,
                                attach_direction="south",
                                connection_family_keys=(ConnectionFamilyKey("road_other"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("west"),
                                offset_x=0,
                                offset_y=2,
                                attach_direction="west",
                                connection_family_keys=(ConnectionFamilyKey("road_other"),),
                            ),
                            PortGeometrySpec(
                                port_id=PortId("east"),
                                offset_x=4,
                                offset_y=2,
                                attach_direction="east",
                                connection_family_keys=(ConnectionFamilyKey("road_other"),),
                            ),
                        ),
                    ),
                ),
                render_style_profiles=(
                    RenderStyleProfile(
                        profile_key=RenderProfileKey("junction/left_custom"),
                    ),
                    RenderStyleProfile(
                        profile_key=RenderProfileKey("junction/right_custom"),
                    ),
                ),
            ),
        )

        candidates = geometry(
            runtime_objects=runtime_objects,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
        )

        self.assertEqual((), candidates)

    def test_locally_unusable_candidate_port_fails_eligibility(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        unusable_right_junction = replace(
            right_junction,
            ports=tuple(
                replace(port, is_active=False)
                if port.port_ref.owner_local_key == PortId("west")
                else port
                for port in right_junction.ports
            ),
        )
        runtime_objects = RuntimeObjectSet(
            junctions=(left_junction, unusable_right_junction),
        )
        eligibility = V1CandidateEligibility()
        schema_view = StaticRouteRequirementSchemaView()
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=schema_view,
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("west"),
            ),
        )

        self.assertFalse(is_eligible)

    def test_candidate_on_inactive_owner_fails_eligibility(self) -> None:
        junction = build_runtime_junctions_for_active_grid(
            build_minimum_active_grid(
                default_x_rail_ids=("x0",),
                authored_tier_rail_ids=("tier_0",),
            )
        )[0]
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            is_active=False,
            ports=(
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("sink_node"),
                        owner_local_key=PortId("in"),
                    ),
                ),
            ),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(sink_node,),
            junctions=(junction,),
        )
        eligibility = V1CandidateEligibility()
        schema_view = StaticRouteRequirementSchemaView(
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("in"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=schema_view,
            frontier_context=FrontierContext(
                current_object_ref=junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=junction.junction_id,
                to_object_ref=NodeId("sink_node"),
                relation_kind="neighbor",
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=NodeId("sink_node"),
                owner_local_key=PortId("in"),
            ),
        )

        self.assertFalse(is_eligible)

    def test_intermediate_non_source_sink_node_candidate_fails_eligibility(self) -> None:
        junction = build_runtime_junctions_for_active_grid(
            build_minimum_active_grid(
                default_x_rail_ids=("x0",),
                authored_tier_rail_ids=("tier_0",),
            )
        )[0]
        intermediate_node = RuntimeNode(
            node_id=NodeId("middle_node"),
            ports=(
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("middle_node"),
                        owner_local_key=PortId("in_left"),
                    ),
                ),
            ),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(intermediate_node,),
            junctions=(junction,),
        )
        eligibility = V1CandidateEligibility()
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=StaticRouteRequirementSchemaView(),
            frontier_context=FrontierContext(
                current_object_ref=junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=junction.junction_id,
                to_object_ref=intermediate_node.node_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=intermediate_node.node_id,
                owner_local_key=PortId("in_left"),
            ),
        )

        self.assertFalse(is_eligible)

    def test_plain_intermediate_active_junction_candidate_port_passes_eligibility(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(
            junctions=(left_junction, right_junction),
        )
        eligibility = V1CandidateEligibility()
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=StaticRouteRequirementSchemaView(),
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("west"),
            ),
        )

        self.assertTrue(is_eligible)

    def test_sink_candidate_port_passes_only_when_allowed_by_schema(self) -> None:
        junction = build_runtime_junctions_for_active_grid(
            build_minimum_active_grid(
                default_x_rail_ids=("x0",),
                authored_tier_rail_ids=("tier_0",),
            )
        )[0]
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            ports=(
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("sink_node"),
                        owner_local_key=PortId("in"),
                    ),
                ),
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("sink_node"),
                        owner_local_key=PortId("out"),
                    ),
                ),
            ),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(sink_node,),
            junctions=(junction,),
        )
        eligibility = V1CandidateEligibility()
        schema_view = StaticRouteRequirementSchemaView(
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("in"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        allowed = eligibility(
            runtime_objects=runtime_objects,
            schema_view=schema_view,
            frontier_context=FrontierContext(
                current_object_ref=junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=junction.junction_id,
                to_object_ref=NodeId("sink_node"),
                relation_kind="neighbor",
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=NodeId("sink_node"),
                owner_local_key=PortId("in"),
            ),
        )

        self.assertTrue(allowed)

    def test_candidate_port_not_allowed_for_requirement_fails_eligibility(self) -> None:
        junction = build_runtime_junctions_for_active_grid(
            build_minimum_active_grid(
                default_x_rail_ids=("x0",),
                authored_tier_rail_ids=("tier_0",),
            )
        )[0]
        sink_node = RuntimeNode(
            node_id=NodeId("sink_node"),
            ports=(
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("sink_node"),
                        owner_local_key=PortId("in"),
                    ),
                ),
                Port(
                    port_ref=PortRef(
                        owner_ref=NodeId("sink_node"),
                        owner_local_key=PortId("out"),
                    ),
                ),
            ),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(sink_node,),
            junctions=(junction,),
        )
        eligibility = V1CandidateEligibility()
        schema_view = StaticRouteRequirementSchemaView(
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("in"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        disallowed = eligibility(
            runtime_objects=runtime_objects,
            schema_view=schema_view,
            frontier_context=FrontierContext(
                current_object_ref=junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=junction.junction_id,
                to_object_ref=NodeId("sink_node"),
                relation_kind="neighbor",
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=NodeId("sink_node"),
                owner_local_key=PortId("out"),
            ),
        )

        self.assertFalse(disallowed)

    def test_eligibility_does_not_embed_global_reachable_sink_logic(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction, right_junction = build_runtime_junctions_for_active_grid(grid)
        runtime_objects = RuntimeObjectSet(
            junctions=(left_junction, right_junction),
        )
        eligibility = V1CandidateEligibility()
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("missing_sink"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=StaticRouteRequirementSchemaView(),
            frontier_context=FrontierContext(
                current_object_ref=left_junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=left_junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=left_junction.junction_id,
                to_object_ref=right_junction.junction_id,
                relation_kind=CROSS_OBJECT_BOUNDARY_RELATION_KIND,
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=PortRef(
                owner_ref=right_junction.junction_id,
                owner_local_key=PortId("west"),
            ),
        )

        self.assertTrue(is_eligible)

    def test_entry_context_with_none_incoming_edge_is_valid_start_context(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::a")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )
        start_context = EntryContext(
            current_port_ref=left_port_ref,
            incoming_edge_id=None,
        )

        self.assertTrue(is_entry_context_usable(state, start_context))

    def test_bidirectional_built_edge_yields_next_entry_contexts_in_both_directions(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::a")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                        traversal_mode="bidirectional",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )

        from_left = directly_reachable_next_entry_contexts(
            state,
            EntryContext(current_port_ref=left_port_ref, incoming_edge_id=None),
        )
        from_right = directly_reachable_next_entry_contexts(
            state,
            EntryContext(current_port_ref=right_port_ref, incoming_edge_id=None),
        )

        self.assertEqual(
            (EntryContext(current_port_ref=right_port_ref, incoming_edge_id=edge_id),),
            from_left,
        )
        self.assertEqual(
            (EntryContext(current_port_ref=left_port_ref, incoming_edge_id=edge_id),),
            from_right,
        )

    def test_unidirectional_built_edge_yields_next_entry_context_only_in_forward_direction(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::a")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                        traversal_mode="a_to_b",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )

        forward = directly_reachable_next_entry_contexts(
            state,
            EntryContext(current_port_ref=left_port_ref, incoming_edge_id=None),
        )
        reverse = directly_reachable_next_entry_contexts(
            state,
            EntryContext(current_port_ref=right_port_ref, incoming_edge_id=None),
        )

        self.assertEqual(
            (EntryContext(current_port_ref=right_port_ref, incoming_edge_id=edge_id),),
            forward,
        )
        self.assertEqual((), reverse)

    def test_inactive_edge_or_unusable_port_yields_no_traversal(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::a")
        inactive_edge_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                        is_active=False,
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )
        unusable_port_state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref, is_active=False),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )
        start_context = EntryContext(
            current_port_ref=left_port_ref,
            incoming_edge_id=None,
        )

        self.assertEqual((), directly_reachable_next_entry_contexts(inactive_edge_state, start_context))
        self.assertEqual((), directly_reachable_next_entry_contexts(unusable_port_state, start_context))

    def test_entry_query_helpers_do_not_mutate_runtime_state(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::a")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=left_port_ref),),
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        ports=(Port(port_ref=right_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=left_port_ref,
                        port_ref_b=right_port_ref,
                        scope="external",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(left_port_ref, right_port_ref),
                edge_ids=(edge_id,),
            ),
        )
        original_state = state

        next_contexts = directly_reachable_next_entry_contexts(
            state,
            EntryContext(current_port_ref=left_port_ref, incoming_edge_id=None),
        )

        self.assertEqual(
            (EntryContext(current_port_ref=right_port_ref, incoming_edge_id=edge_id),),
            next_contexts,
        )
        self.assertEqual(original_state, state)

    def test_every_active_grid_intersection_gets_a_runtime_junction(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        runtime_junctions = build_runtime_junctions_for_active_grid(grid)
        runtime_junction_ids = {runtime_junction.junction_id for runtime_junction in runtime_junctions}
        expected_junction_ids = {
            Junction(x_rail_id=x_rail.rail_id, y_rail_id=y_rail.rail_id)
            for x_rail in grid.x_rails
            for y_rail in grid.y_rails
        }

        self.assertEqual(expected_junction_ids, runtime_junction_ids)
        self.assertEqual(len(expected_junction_ids), len(runtime_junctions))

    def test_runtime_junction_creation_works_from_minimal_active_grid(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junctions = build_runtime_junctions_for_active_grid(grid)

        self.assertEqual(1, len(runtime_junctions))
        self.assertEqual(
            Junction(
                x_rail_id=LogicalXRailId("x0"),
                y_rail_id=LogicalYRailId("tier_0"),
            ),
            runtime_junctions[0].junction_id,
        )

    def test_each_runtime_junction_gets_the_expected_default_port_set(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]
        port_local_keys = {port.port_ref.owner_local_key for port in runtime_junction.ports}

        self.assertEqual(
            {
                PortId("north"),
                PortId("south"),
                PortId("west"),
                PortId("east"),
            },
            port_local_keys,
        )

    def test_junction_owned_ports_have_the_correct_owner_reference(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]

        self.assertTrue(
            all(
                port.port_ref.owner_ref == runtime_junction.junction_id
                for port in runtime_junction.ports
            )
        )

    def test_junction_port_identity_is_owner_scoped(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junctions = build_runtime_junctions_for_active_grid(grid)
        west_port_refs = [
            next(
                port.port_ref
                for port in runtime_junction.ports
                if port.port_ref.owner_local_key == PortId("west")
            )
            for runtime_junction in runtime_junctions
        ]

        self.assertEqual(2, len(west_port_refs))
        self.assertNotEqual(west_port_refs[0], west_port_refs[1])
        self.assertNotEqual(west_port_refs[0].owner_ref, west_port_refs[1].owner_ref)

    def test_logical_junction_values_remain_distinct_from_runtime_junction_objects(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]
        logical_junction = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )

        self.assertIsInstance(runtime_junction, RuntimeJunction)
        self.assertEqual(logical_junction, runtime_junction.junction_id)
        self.assertNotIsInstance(logical_junction, RuntimeJunction)

    def test_runtime_junction_builder_sets_default_occupancy_and_activity_state(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junction = build_runtime_junctions_for_active_grid(grid)[0]

        self.assertTrue(runtime_junction.is_active)
        self.assertIsNone(runtime_junction.occupying_node_id)
        self.assertEqual(4, len(runtime_junction.ports))

    def test_empty_runtime_junctions_exist_without_rendering_or_path_objects(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )

        runtime_junctions = build_runtime_junctions_for_active_grid(grid)
        objects = RuntimeObjectSet(junctions=runtime_junctions)

        self.assertEqual(len(runtime_junctions), len(objects.junctions))
        self.assertTrue(
            all(
                junction.render_profile.profile_key == DEFAULT_PLAIN_JUNCTION_PROFILE_KEY
                for junction in runtime_junctions
            )
        )
        self.assertTrue(all(junction.attributes == () for junction in runtime_junctions))
        self.assertTrue(all(len(junction.ports) == 4 for junction in runtime_junctions))
        self.assertEqual((), objects.edges)
        self.assertFalse(hasattr(solver_runtime, "Path"))

    def test_port_ref_rejects_unknown_owner_ref_type(self) -> None:
        with self.assertRaises(TypeError):
            PortRef(
                owner_ref=123,  # type: ignore[arg-type]
                owner_local_key=PortId("east_out"),
            )

    def test_runtime_objects_default_schema_refs_to_identity(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )

        node_port = Port(
            port_ref=PortRef(
                owner_ref=NodeId("node_a"),
                owner_local_key=PortId("east_out"),
            ),
        )
        junction_port = Port(
            port_ref=PortRef(
                owner_ref=junction_id,
                owner_local_key=PortId("west"),
            ),
        )

        node = RuntimeNode(
            node_id=NodeId("node_a"),
            ports=(node_port,),
        )
        junction = RuntimeJunction(
            junction_id=junction_id,
            ports=(junction_port,),
        )

        self.assertEqual(NodeId("node_a"), node.schema_node_id)
        self.assertEqual(junction_id, junction.schema_junction_id)
        self.assertEqual(PortId("east_out"), node_port.definition_port_id)
        self.assertIsNone(junction_port.definition_port_id)
        self.assertTrue(is_object_ref_active(RuntimeObjectSet(nodes=(node,), junctions=(junction,)), NodeId("node_a")))

    def test_schema_definitions_accept_render_profile_refs(self) -> None:
        definition = NodeDefinition(
            node_id=NodeId("node_a"),
            kind="generic",
            ports=(
                PortDefinition(
                    port_id=PortId("east_out"),
                    orientation="east",
                    capacity=1,
                    render_profile=RenderProfileRef(
                        profile_key=RenderProfileKey("port_profile")
                    ),
                ),
            ),
            render_profile=RenderProfileRef(
                profile_key=RenderProfileKey("node_profile")
            ),
        )

        self.assertEqual(
            RenderProfileKey("node_profile"),
            definition.render_profile.profile_key,
        )
        self.assertEqual(
            RenderProfileKey("port_profile"),
            definition.ports[0].render_profile.profile_key,
        )

    def test_port_definition_default_capacity_is_unbounded(self) -> None:
        definition = PortDefinition(
            port_id=PortId("east_out"),
            orientation="east",
        )

        self.assertIsNone(definition.capacity)

    def test_valid_internal_edge(self) -> None:
        owner_ref = NodeId("node_a")
        edge = PortEdge(
            edge_id=PortEdgeId("edge::internal"),
            port_ref_a=PortRef(
                owner_ref=owner_ref,
                owner_local_key=PortId("west"),
            ),
            port_ref_b=PortRef(
                owner_ref=owner_ref,
                owner_local_key=PortId("east"),
            ),
            scope="internal",
            owner_object_ref=owner_ref,
        )

        self.assertEqual("internal", edge.scope)
        self.assertEqual(owner_ref, edge.owner_object_ref)

    def test_invalid_internal_edge_requires_owner_object_ref(self) -> None:
        owner_ref = NodeId("node_a")

        with self.assertRaises(ValueError):
            PortEdge(
                edge_id=PortEdgeId("edge::internal"),
                port_ref_a=PortRef(
                    owner_ref=owner_ref,
                    owner_local_key=PortId("west"),
                ),
                port_ref_b=PortRef(
                    owner_ref=owner_ref,
                    owner_local_key=PortId("east"),
                ),
                scope="internal",
            )

    def test_invalid_internal_edge_requires_endpoints_to_match_owner(self) -> None:
        with self.assertRaises(ValueError):
            PortEdge(
                edge_id=PortEdgeId("edge::internal"),
                port_ref_a=PortRef(
                    owner_ref=NodeId("node_a"),
                    owner_local_key=PortId("west"),
                ),
                port_ref_b=PortRef(
                    owner_ref=NodeId("node_b"),
                    owner_local_key=PortId("east"),
                ),
                scope="internal",
                owner_object_ref=NodeId("node_a"),
            )

    def test_valid_external_edge_has_no_owner_object_ref(self) -> None:
        edge = PortEdge(
            edge_id=PortEdgeId("edge::external"),
            port_ref_a=PortRef(
                owner_ref=NodeId("node_a"),
                owner_local_key=PortId("east"),
            ),
            port_ref_b=PortRef(
                owner_ref=NodeId("node_b"),
                owner_local_key=PortId("west"),
            ),
            scope="external",
        )

        self.assertEqual("external", edge.scope)
        self.assertIsNone(edge.owner_object_ref)

    def test_port_edge_model_stays_minimal_and_keeps_render_type_out(self) -> None:
        edge = PortEdge(
            edge_id=PortEdgeId("edge::external"),
            port_ref_a=PortRef(
                owner_ref=NodeId("node_a"),
                owner_local_key=PortId("east"),
            ),
            port_ref_b=PortRef(
                owner_ref=NodeId("node_b"),
                owner_local_key=PortId("west"),
            ),
            scope="external",
        )

        self.assertEqual(
            {
                "edge_id",
                "port_ref_a",
                "port_ref_b",
                "scope",
                "traversal_mode",
                "owner_object_ref",
                "is_active",
                "attributes",
            },
            set(edge.__dataclass_fields__),
        )
        self.assertFalse(hasattr(edge, "structural_kind"))
        self.assertFalse(hasattr(edge, "render_profile"))

    def test_inactive_junction_makes_its_ports_unusable(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        junction_port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )
        objects = RuntimeObjectSet(
            junctions=(
                RuntimeJunction(
                    junction_id=junction_id,
                    is_active=False,
                    ports=(Port(port_ref=junction_port_ref, is_active=True),),
                ),
            ),
        )

        self.assertFalse(is_object_ref_active(objects, junction_id))
        self.assertFalse(is_port_ref_usable(objects, junction_port_ref))

    def test_edge_connected_to_unusable_port_remains_stored_but_is_not_usable(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        node_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        junction_port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )
        edge_id = PortEdgeId("edge::external")
        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        ports=(Port(port_ref=node_port_ref),),
                    ),
                ),
                junctions=(
                    RuntimeJunction(
                        junction_id=junction_id,
                        is_active=False,
                        ports=(Port(port_ref=junction_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=edge_id,
                        port_ref_a=node_port_ref,
                        port_ref_b=junction_port_ref,
                        scope="external",
                        is_active=True,
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(node_port_ref, junction_port_ref),
                edge_ids=(edge_id,),
            ),
        )

        self.assertEqual((edge_id,), state.graph.edge_ids)
        self.assertEqual(edge_id, state.objects.edges[0].edge_id)
        self.assertFalse(is_edge_id_usable(state.objects, edge_id))

    def test_active_state_is_reversible_by_replacing_runtime_objects(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )
        active_junction = RuntimeJunction(
            junction_id=junction_id,
            ports=(Port(port_ref=port_ref),),
        )
        inactive_junction = replace(active_junction, is_active=False)
        active_objects = RuntimeObjectSet(junctions=(active_junction,))
        inactive_objects = RuntimeObjectSet(junctions=(inactive_junction,))

        self.assertTrue(is_port_ref_usable(active_objects, port_ref))
        self.assertFalse(is_port_ref_usable(inactive_objects, port_ref))

    def test_full_port_remains_usable_but_rejects_new_attachment(self) -> None:
        left_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east"),
        )
        right_port_ref = PortRef(
            owner_ref=NodeId("node_b"),
            owner_local_key=PortId("west"),
        )
        objects = RuntimeObjectSet(
            nodes=(
                RuntimeNode(
                    node_id=NodeId("node_a"),
                    ports=(Port(port_ref=left_port_ref, capacity=1),),
                ),
                RuntimeNode(
                    node_id=NodeId("node_b"),
                    ports=(Port(port_ref=right_port_ref),),
                ),
            ),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::a"),
                    port_ref_a=left_port_ref,
                    port_ref_b=right_port_ref,
                    scope="external",
                ),
            ),
        )

        self.assertTrue(is_port_ref_usable(objects, left_port_ref))
        self.assertEqual(1, direct_attachment_count(objects, left_port_ref))
        self.assertFalse(can_port_ref_accept_new_attachment(objects, left_port_ref))

    def test_full_candidate_port_fails_eligibility(self) -> None:
        junction = build_runtime_junctions_for_active_grid(
            build_minimum_active_grid(
                default_x_rail_ids=("x0",),
                authored_tier_rail_ids=("tier_0",),
            )
        )[0]
        sink_port_ref = PortRef(
            owner_ref=NodeId("sink_node"),
            owner_local_key=PortId("in"),
        )
        existing_port_ref = PortRef(
            owner_ref=NodeId("existing_node"),
            owner_local_key=PortId("out"),
        )
        runtime_objects = RuntimeObjectSet(
            nodes=(
                RuntimeNode(
                    node_id=NodeId("sink_node"),
                    ports=(Port(port_ref=sink_port_ref, capacity=1),),
                ),
                RuntimeNode(
                    node_id=NodeId("existing_node"),
                    ports=(Port(port_ref=existing_port_ref),),
                ),
            ),
            junctions=(junction,),
            edges=(
                PortEdge(
                    edge_id=PortEdgeId("edge::existing_to_sink"),
                    port_ref_a=existing_port_ref,
                    port_ref_b=sink_port_ref,
                    scope="external",
                ),
            ),
        )
        eligibility = V1CandidateEligibility()
        schema_view = StaticRouteRequirementSchemaView(
            sink_allowances=(
                RouteRequirementPortAllowance(
                    object_ref=NodeId("sink_node"),
                    requirement_kind="flow",
                    port_local_keys=(PortId("in"),),
                ),
            ),
        )
        route_requirement = RouteRequirement(
            requirement_id="req::a",
            source_object_ref=NodeId("source_node"),
            sink_object_ref=NodeId("sink_node"),
            requirement_kind="flow",
        )

        is_eligible = eligibility(
            runtime_objects=runtime_objects,
            schema_view=schema_view,
            frontier_context=FrontierContext(
                current_object_ref=junction.junction_id,
                current_port_ref=PortRef(
                    owner_ref=junction.junction_id,
                    owner_local_key=PortId("east"),
                ),
            ),
            neighbor_relation=NeighborRelation(
                from_object_ref=junction.junction_id,
                to_object_ref=NodeId("sink_node"),
                relation_kind="neighbor",
                approach_direction="east",
            ),
            route_requirement=route_requirement,
            candidate_port_ref=sink_port_ref,
        )

        self.assertFalse(is_eligible)

    def test_no_path_object_is_introduced(self) -> None:
        self.assertFalse(hasattr(solver_runtime, "Path"))
        self.assertNotIn("Path", getattr(solver_types, "__all__", ()))

    def test_port_graph_state_keeps_objects_and_graph_separate(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        node_port_ref = PortRef(
            owner_ref=NodeId("node_a"),
            owner_local_key=PortId("east_out"),
        )
        junction_port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )

        state = PortGraphState(
            objects=RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        current_junction_id=junction_id,
                        is_active=True,
                        ports=(Port(port_ref=node_port_ref),),
                        render_profile=RenderProfileRef(
                            profile_key=RenderProfileKey("node_profile")
                        ),
                    ),
                ),
                junctions=(
                    RuntimeJunction(
                        junction_id=junction_id,
                        occupying_node_id=NodeId("node_a"),
                        is_active=False,
                        ports=(Port(port_ref=junction_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::a"),
                        port_ref_a=node_port_ref,
                        port_ref_b=junction_port_ref,
                        scope="external",
                    ),
                ),
            ),
            graph=PortGraphIndex(
                port_refs=(node_port_ref, junction_port_ref),
                edge_ids=(PortEdgeId("edge::a"),),
            ),
        )

        self.assertEqual(node_port_ref, state.graph.port_refs[0])
        self.assertEqual((PortEdgeId("edge::a"),), state.graph.edge_ids)
        self.assertEqual(
            node_port_ref,
            state.objects.nodes[0].ports[0].port_ref,
        )
        self.assertEqual(PortEdgeId("edge::a"), state.objects.edges[0].edge_id)

    def test_port_graph_state_rejects_unresolved_graph_ref(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        junction_port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )

        with self.assertRaises(ValueError):
            PortGraphState(
                objects=RuntimeObjectSet(
                    junctions=(
                        RuntimeJunction(
                            junction_id=junction_id,
                            ports=(Port(port_ref=junction_port_ref),),
                        ),
                    ),
                ),
                graph=PortGraphIndex(
                    port_refs=(
                        PortRef(
                            owner_ref=junction_id,
                            owner_local_key=PortId("missing"),
                        ),
                    ),
                ),
            )

    def test_runtime_object_set_rejects_edge_to_unknown_port(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        junction_port_ref = PortRef(
            owner_ref=junction_id,
            owner_local_key=PortId("west"),
        )

        with self.assertRaises(ValueError):
            RuntimeObjectSet(
                junctions=(
                    RuntimeJunction(
                        junction_id=junction_id,
                        ports=(Port(port_ref=junction_port_ref),),
                    ),
                ),
                edges=(
                    PortEdge(
                        edge_id=PortEdgeId("edge::a"),
                        port_ref_a=junction_port_ref,
                        port_ref_b=PortRef(
                            owner_ref=NodeId("node_a"),
                            owner_local_key=PortId("east_out"),
                        ),
                        scope="external",
                    ),
                ),
            )

    def test_runtime_object_set_rejects_inconsistent_occupancy_lookup(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )
        other_junction_id = Junction(
            x_rail_id=LogicalXRailId("x1"),
            y_rail_id=LogicalYRailId("tier_0"),
        )

        with self.assertRaises(ValueError):
            RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        current_junction_id=junction_id,
                    ),
                    RuntimeNode(
                        node_id=NodeId("node_b"),
                        current_junction_id=other_junction_id,
                    ),
                ),
                junctions=(
                    RuntimeJunction(
                        junction_id=junction_id,
                        occupying_node_id=NodeId("node_b"),
                        is_active=False,
                    ),
                    RuntimeJunction(
                        junction_id=other_junction_id,
                    ),
                ),
            )

    def test_runtime_object_set_rejects_active_occupied_junction(self) -> None:
        junction_id = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("tier_0"),
        )

        with self.assertRaises(ValueError):
            RuntimeObjectSet(
                nodes=(
                    RuntimeNode(
                        node_id=NodeId("node_a"),
                        current_junction_id=junction_id,
                    ),
                ),
                junctions=(
                    RuntimeJunction(
                        junction_id=junction_id,
                        occupying_node_id=NodeId("node_a"),
                        is_active=True,
                    ),
                ),
            )

    def test_node_definition_rejects_duplicate_port_ids(self) -> None:
        with self.assertRaises(ValueError):
            NodeDefinition(
                node_id=NodeId("node_a"),
                kind="generic",
                ports=(
                    PortDefinition(
                        port_id=PortId("out"),
                        orientation="east",
                        capacity=1,
                    ),
                    PortDefinition(
                        port_id=PortId("out"),
                        orientation="west",
                        capacity=1,
                    ),
                ),
            )

    def test_node_domain_can_represent_empty_junction_set(self) -> None:
        domain = NodeDomain(
            node_id=NodeId("node_a"),
            junctions=frozenset(),
        )

        self.assertEqual(frozenset(), domain.junctions)

    def test_active_grid_state_rejects_dynamic_rail_missing_from_band(self) -> None:
        with self.assertRaises(ValueError):
            ActiveGridState(
                x_rails=(LogicalXRail(rail_id=LogicalXRailId("x0"), order=0),),
                y_rails=(
                    LogicalYRail(
                        rail_id=LogicalYRailId("tier_0"),
                        logical_rank=Fraction(0, 1),
                        kind="authored",
                        authored_tier_index=0,
                    ),
                    LogicalYRail(
                        rail_id=LogicalYRailId("tier_1"),
                        logical_rank=Fraction(1, 1),
                        kind="authored",
                        authored_tier_index=1,
                    ),
                    LogicalYRail(
                        rail_id=LogicalYRailId("dyn_a"),
                        logical_rank=Fraction(1, 2),
                        kind="dynamic",
                        band_id=BandId("band::tier_0::tier_1"),
                    ),
                ),
                y_bands=(
                    YRailBandState(
                        band_id=BandId("band::tier_0::tier_1"),
                        upper_authored_rail_id=LogicalYRailId("tier_0"),
                        lower_authored_rail_id=LogicalYRailId("tier_1"),
                        dynamic_rail_ids=(),
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
