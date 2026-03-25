from __future__ import annotations

import unittest

from toolsv2.base_renderer import build_v1_base_renderer
from toolsv2.production_node_definitions import (
    build_v1_and_knot_node_definition,
    build_v1_production_visual_profile_catalog,
    build_v1_skill_frame_node_definition,
)
from toolsv2.profile import build_minimum_active_grid
from toolsv2.render_mapper import build_v1_vanilla_render_mapper
from toolsv2.render_template_loader import build_cached_render_template_loader
from toolsv2.runtime_snapshot_builder import build_v1_runtime_snapshot_builder
from toolsv2.solver_common import Junction, NodeDomain, NodeId, PortEdgeId, PortId, PortRef
from toolsv2.solver_runtime import PortEdge, PortGraphIndex, PortGraphState, RuntimeObjectSet
from toolsv2.placement_solver import PlacementSeed
from toolsv2.visual_profiles import (
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
    RenderTransformSpec,
)
from toolsv2.source_art_catalog import build_v1_source_render_templates


class BaseRendererTests(unittest.TestCase):
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

    def test_base_renderer_renders_skill_frame_over_default_background(self) -> None:
        node_id = NodeId("skill_a")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {node_id: build_v1_skill_frame_node_definition(node_id)},
        )(
            self._build_seed(
                {
                    node_id: Junction(x_rail_id="x0", y_rail_id="tier_0"),
                }
            )
        )
        renderer = build_v1_base_renderer()
        mapper = build_v1_vanilla_render_mapper(active_grid)
        visual_catalog = build_v1_production_visual_profile_catalog()

        result = renderer(
            state,
            mapper,
            visual_catalog,
        )

        self.assertEqual((163, 257), result.image.size)
        self.assertEqual((163, 257), result.background_image.size)
        self.assertEqual(1, len(result.resolved_objects))
        self.assertEqual(2, len(result.instructions))
        self.assertTrue(any(layer.layer_id == "object_body" for layer in result.layer_images))

        body_template = next(
            template
            for template in build_v1_source_render_templates()
            if template.template_key == DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY
        )
        body_image = build_cached_render_template_loader().load(body_template).image
        assert body_image is not None
        self.assertEqual(body_image.getpixel((15, 15)), result.image.getpixel((24, 55)))

    def test_base_renderer_renders_external_straight_span_between_adjacent_and_knots(self) -> None:
        left_node_id = NodeId("and_left")
        right_node_id = NodeId("and_right")
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )
        state = build_v1_runtime_snapshot_builder(
            active_grid,
            {
                left_node_id: build_v1_and_knot_node_definition(left_node_id),
                right_node_id: build_v1_and_knot_node_definition(right_node_id),
            },
        )(
            self._build_seed(
                {
                    left_node_id: Junction(x_rail_id="x0", y_rail_id="tier_0"),
                    right_node_id: Junction(x_rail_id="x1", y_rail_id="tier_0"),
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
        renderer = build_v1_base_renderer()
        mapper = build_v1_vanilla_render_mapper(active_grid)
        visual_catalog = build_v1_production_visual_profile_catalog()

        result = renderer(
            state,
            mapper,
            visual_catalog,
        )

        self.assertTrue(any(layer.layer_id == "road" for layer in result.layer_images))

        background_pixel = result.image.getpixel((33, 40))
        road_boundary_pixel = result.image.getpixel((33, 54))
        road_center_pixel = result.image.getpixel((33, 55))
        road_lower_boundary_pixel = result.image.getpixel((33, 56))
        self.assertNotEqual(background_pixel, road_center_pixel)

        straight_template = next(
            template
            for template in build_v1_source_render_templates()
            if template.template_key == DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY
        )
        rotated_straight = build_cached_render_template_loader().load(
            straight_template,
            RenderTransformSpec(quarter_turns_clockwise=1),
        ).image
        assert rotated_straight is not None
        self.assertEqual(rotated_straight.getpixel((0, 0)), road_boundary_pixel)
        self.assertEqual(rotated_straight.getpixel((0, 1)), road_center_pixel)
        self.assertEqual(rotated_straight.getpixel((0, 2)), road_lower_boundary_pixel)


if __name__ == "__main__":
    unittest.main()
