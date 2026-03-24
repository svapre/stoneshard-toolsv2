from __future__ import annotations

import unittest

from toolsv2.production_node_definitions import (
    build_v1_and_knot_node_definition,
    build_v1_production_visual_profile_catalog,
    build_v1_skill_frame_node_definition,
)
from toolsv2.profile import build_minimum_active_grid
from toolsv2.render_resolver import build_v1_render_resolver
from toolsv2.runtime_snapshot_builder import build_v1_runtime_snapshot_builder
from toolsv2.solver_common import Junction, PortEdgeId, PortRef
from toolsv2.solver_runtime import PortEdge, PortGraphIndex, PortGraphState, RuntimeObjectSet
from toolsv2.solver_types import EdgeTraversalMode, NodeDomain, NodeId, PortId
from toolsv2.placement_solver import PlacementSeed
from toolsv2.visual_profiles import DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY


class _StubMapper:
    def __init__(self, x_pixels: dict[str, int], y_pixels: dict[str, int]) -> None:
        self._x_pixels = x_pixels
        self._y_pixels = y_pixels

    def x_pixel_for(self, rail_id) -> int:
        return self._x_pixels[str(rail_id)]

    def y_pixel_for(self, rail_id) -> int:
        return self._y_pixels[str(rail_id)]


class RenderResolverTests(unittest.TestCase):
    def _build_seed(self, assignments: dict[NodeId, Junction]) -> PlacementSeed:
        return PlacementSeed(
            domains={
                node_id: NodeDomain(node_id=node_id, junctions=frozenset({junction}))
                for node_id, junction in assignments.items()
            },
            assignments=assignments,
        )

    def _all_port_refs(self, state: PortGraphState) -> tuple[PortRef, ...]:
        return tuple(
            port.port_ref
            for owner in (*state.objects.nodes, *state.objects.junctions)
            for port in owner.ports
        )

    def _with_edges(
        self,
        state: PortGraphState,
        *edges: PortEdge,
    ) -> PortGraphState:
        return PortGraphState(
            objects=RuntimeObjectSet(
                nodes=state.objects.nodes,
                junctions=state.objects.junctions,
                edges=state.objects.edges + tuple(edges),
            ),
            graph=PortGraphIndex(
                port_refs=self._all_port_refs(state),
                edge_ids=state.graph.edge_ids + tuple(edge.edge_id for edge in edges),
                attributes=state.graph.attributes,
            ),
        )

    def test_resolver_emits_node_render_spec_with_resolved_anchor_and_ports(self) -> None:
        node_id = NodeId("skill_a")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        junction = Junction(x_rail_id="x0", y_rail_id="tier_0")
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {node_id: build_v1_skill_frame_node_definition(node_id)},
        )(self._build_seed({node_id: junction}))

        resolved = build_v1_render_resolver()(
            state,
            _StubMapper({"x0": 100}, {"tier_0": 200}),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(1, len(resolved))
        node_spec = resolved[0]
        self.assertEqual(node_id, node_spec.instance_ref)
        self.assertEqual((100, 200), (node_spec.anchor_x, node_spec.anchor_y))
        self.assertEqual(
            {
                PortId("top"): (100, 185, "north"),
                PortId("bottom"): (100, 214, "south"),
            },
            {
                port.port_id: (port.pixel_x, port.pixel_y, port.attach_direction)
                for port in node_spec.ports
            },
        )

    def test_resolver_omits_separate_spec_for_occupied_junction_and_empty_unoccupied_junction(self) -> None:
        node_id = NodeId("skill_a")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        occupied_junction = Junction(x_rail_id="x0", y_rail_id="tier_0")
        unoccupied_junction = Junction(x_rail_id="x1", y_rail_id="tier_0")
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {node_id: build_v1_skill_frame_node_definition(node_id)},
        )(self._build_seed({node_id: occupied_junction}))

        resolved = build_v1_render_resolver()(
            state,
            _StubMapper({"x0": 100, "x1": 140}, {"tier_0": 200}),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual((node_id,), tuple(spec.instance_ref for spec in resolved))
        self.assertNotIn(unoccupied_junction, tuple(spec.instance_ref for spec in resolved))

    def test_resolver_emits_unoccupied_junction_only_when_built_local_connections_exist(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0",),
        )
        empty_state = build_v1_runtime_snapshot_builder(active_grid, {})(
            self._build_seed({})
        )
        junction = empty_state.objects.junctions[0]
        state = self._with_edges(
            empty_state,
            PortEdge(
                edge_id=PortEdgeId("edge::junction_internal"),
                port_ref_a=PortRef(junction.junction_id, PortId("north")),
                port_ref_b=PortRef(junction.junction_id, PortId("east")),
                scope="internal",
                traversal_mode="bidirectional",
                owner_object_ref=junction.junction_id,
            ),
        )

        resolved = build_v1_render_resolver()(
            state,
            _StubMapper({"x0": 100}, {"tier_0": 200}),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(1, len(resolved))
        junction_spec = resolved[0]
        self.assertEqual(junction.junction_id, junction_spec.instance_ref)
        self.assertEqual(1, len(junction_spec.local_connections))
        self.assertEqual(
            (
                PortId("north"),
                PortId("east"),
                DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
            ),
            (
                junction_spec.local_connections[0].from_port_id,
                junction_spec.local_connections[0].to_port_id,
                junction_spec.local_connections[0].connection_family_key,
            ),
        )

    def test_resolver_emits_axis_aligned_external_span_as_separate_edge_spec(self) -> None:
        left_node_id = NodeId("and_left")
        right_node_id = NodeId("and_right")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0",),
        )
        left_junction = Junction(x_rail_id="x0", y_rail_id="tier_0")
        right_junction = Junction(x_rail_id="x1", y_rail_id="tier_0")
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {
                left_node_id: build_v1_and_knot_node_definition(left_node_id),
                right_node_id: build_v1_and_knot_node_definition(right_node_id),
            },
        )(
            self._build_seed(
                {
                    left_node_id: left_junction,
                    right_node_id: right_junction,
                }
            )
        )
        state = self._with_edges(
            state,
            PortEdge(
                edge_id=PortEdgeId("edge::horizontal"),
                port_ref_a=PortRef(left_node_id, PortId("right")),
                port_ref_b=PortRef(right_node_id, PortId("left")),
                scope="external",
                traversal_mode="bidirectional",
            ),
        )

        resolved = build_v1_render_resolver()(
            state,
            _StubMapper({"x0": 100, "x1": 140}, {"tier_0": 200}),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(
            (left_node_id, right_node_id, PortEdgeId("edge::horizontal")),
            tuple(spec.instance_ref for spec in resolved),
        )
        edge_spec = resolved[-1]
        self.assertEqual(1, len(edge_spec.spans))
        self.assertEqual(
            (101, 200, 139, 200),
            (
                edge_spec.spans[0].start_x,
                edge_spec.spans[0].start_y,
                edge_spec.spans[0].end_x,
                edge_spec.spans[0].end_y,
            ),
        )

    def test_resolver_rejects_non_axis_aligned_external_span_in_v1(self) -> None:
        left_node_id = NodeId("and_left")
        lower_node_id = NodeId("and_lower")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        upper_left_junction = Junction(x_rail_id="x0", y_rail_id="tier_0")
        lower_right_junction = Junction(x_rail_id="x1", y_rail_id="tier_1")
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {
                left_node_id: build_v1_and_knot_node_definition(left_node_id),
                lower_node_id: build_v1_and_knot_node_definition(lower_node_id),
            },
        )(
            self._build_seed(
                {
                    left_node_id: upper_left_junction,
                    lower_node_id: lower_right_junction,
                }
            )
        )
        state = self._with_edges(
            state,
            PortEdge(
                edge_id=PortEdgeId("edge::diagonal"),
                port_ref_a=PortRef(left_node_id, PortId("right")),
                port_ref_b=PortRef(lower_node_id, PortId("top")),
                scope="external",
                traversal_mode="bidirectional",
            ),
        )

        with self.assertRaises(ValueError):
            build_v1_render_resolver()(
                state,
                _StubMapper({"x0": 100, "x1": 140}, {"tier_0": 200, "tier_1": 240}),
                build_v1_production_visual_profile_catalog(),
            )


if __name__ == "__main__":
    unittest.main()
