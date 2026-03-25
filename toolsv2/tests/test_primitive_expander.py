from __future__ import annotations

import unittest

from toolsv2.primitive_expander import build_v1_primitive_expander
from toolsv2.production_node_definitions import (
    build_v1_production_visual_profile_catalog,
)
from toolsv2.render_contracts import (
    PixelMaskStampInstruction,
    RepeatedSpanInstruction,
    ResolvedLocalConnectionSpec,
    ResolvedObjectRenderSpec,
    ResolvedSpanSpec,
    SpriteStampInstruction,
)
from toolsv2.solver_common import PortEdgeId, PortId, RenderProfileKey
from toolsv2.visual_profiles import (
    COMPOSITION_OVERWRITE,
    ConnectionFamilyKey,
    DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
    DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
    DEFAULT_OBJECT_BODY_LAYER_ID,
    DEFAULT_ROAD_LAYER_ID,
    DEFAULT_SHADOW_LAYER_ID,
    DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_PROFILE_KEY,
    DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
    RenderTransformSpec,
)


class PrimitiveExpanderTests(unittest.TestCase):
    def test_node_style_profile_expands_to_sprite_stamps(self) -> None:
        instructions = build_v1_primitive_expander()(
            (
                ResolvedObjectRenderSpec(
                    instance_ref="skill_a",
                    profile_key=DEFAULT_SKILL_FRAME_PROFILE_KEY,
                    anchor_x=100,
                    anchor_y=200,
                ),
            ),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(2, len(instructions))
        self.assertEqual(
            (
                SpriteStampInstruction(
                    layer_id=DEFAULT_SHADOW_LAYER_ID,
                    template_key=DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
                    anchor_x=100,
                    anchor_y=215,
                    transform=RenderTransformSpec(),
                    composition_operator=COMPOSITION_OVERWRITE,
                ),
                SpriteStampInstruction(
                    layer_id=DEFAULT_OBJECT_BODY_LAYER_ID,
                    template_key=DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
                    anchor_x=100,
                    anchor_y=200,
                    transform=RenderTransformSpec(),
                    composition_operator=COMPOSITION_OVERWRITE,
                ),
            ),
            instructions,
        )

    def test_axis_aligned_horizontal_span_expands_to_repeated_span_instruction(self) -> None:
        instructions = build_v1_primitive_expander()(
            (
                ResolvedObjectRenderSpec(
                    instance_ref=PortEdgeId("edge::horizontal"),
                    profile_key=RenderProfileKey("edge_family/road_external_straight"),
                    anchor_x=101,
                    anchor_y=200,
                    spans=(
                        ResolvedSpanSpec(
                            connection_family_key=DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
                            start_x=101,
                            start_y=200,
                            end_x=139,
                            end_y=200,
                        ),
                    ),
                ),
            ),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(
            (
                RepeatedSpanInstruction(
                    layer_id=DEFAULT_ROAD_LAYER_ID,
                    connection_family_key=DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
                    template_key=DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                    start_x=101,
                    start_y=200,
                    end_x=139,
                    end_y=200,
                    transform=RenderTransformSpec(quarter_turns_clockwise=1),
                    composition_operator=COMPOSITION_OVERWRITE,
                ),
            ),
            instructions,
        )

    def test_axis_aligned_vertical_span_expands_to_repeated_span_instruction(self) -> None:
        instructions = build_v1_primitive_expander()(
            (
                ResolvedObjectRenderSpec(
                    instance_ref=PortEdgeId("edge::vertical"),
                    profile_key=RenderProfileKey("edge_family/road_external_straight"),
                    anchor_x=100,
                    anchor_y=185,
                    spans=(
                        ResolvedSpanSpec(
                            connection_family_key=DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
                            start_x=100,
                            start_y=185,
                            end_x=100,
                            end_y=214,
                        ),
                    ),
                ),
            ),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(
            (
                RepeatedSpanInstruction(
                    layer_id=DEFAULT_ROAD_LAYER_ID,
                    connection_family_key=DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
                    template_key=DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                    start_x=100,
                    start_y=185,
                    end_x=100,
                    end_y=214,
                    transform=RenderTransformSpec(),
                    composition_operator=COMPOSITION_OVERWRITE,
                ),
            ),
            instructions,
        )

    def test_local_connection_piece_expands_from_profile_binding(self) -> None:
        instructions = build_v1_primitive_expander()(
            (
                ResolvedObjectRenderSpec(
                    instance_ref="junction_a",
                    profile_key=RenderProfileKey("junction/plain"),
                    anchor_x=100,
                    anchor_y=200,
                    local_connections=(
                        ResolvedLocalConnectionSpec(
                            from_port_id=PortId("north"),
                            to_port_id=PortId("east"),
                            connection_family_key=DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
                        ),
                    ),
                ),
            ),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(
            (
                SpriteStampInstruction(
                    layer_id=DEFAULT_ROAD_LAYER_ID,
                    template_key=DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
                    anchor_x=100,
                    anchor_y=200,
                    transform=RenderTransformSpec(),
                    composition_operator=COMPOSITION_OVERWRITE,
                ),
            ),
            instructions,
        )

    def test_node_without_style_bindings_but_with_only_spans_is_allowed(self) -> None:
        instructions = build_v1_primitive_expander()(
            (
                ResolvedObjectRenderSpec(
                    instance_ref=PortEdgeId("edge::only"),
                    profile_key=RenderProfileKey("edge_family/road_external_straight"),
                    anchor_x=0,
                    anchor_y=0,
                    spans=(
                        ResolvedSpanSpec(
                            connection_family_key=ConnectionFamilyKey("road_external_straight"),
                            start_x=0,
                            start_y=0,
                            end_x=10,
                            end_y=0,
                        ),
                    ),
                ),
            ),
            build_v1_production_visual_profile_catalog(),
        )

        self.assertEqual(1, len(instructions))
        self.assertIsInstance(instructions[0], RepeatedSpanInstruction)


if __name__ == "__main__":
    unittest.main()
