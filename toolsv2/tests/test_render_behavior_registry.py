from __future__ import annotations

import unittest

from PIL import Image

from toolsv2.render_behavior_registry import (
    build_v1_render_behavior_registry,
    compose_local_block_finalizer_rule,
    max_light_composition_rule,
)
from toolsv2.render_contracts import RasterStampInstruction, ResolvedLocalConnectionSpec, ResolvedObjectRenderSpec, ResolvedPortRenderSpec, SpriteStampInstruction
from toolsv2.render_template_loader import LoadedRenderTemplate, build_cached_render_template_loader
from toolsv2.solver_common import PortId, RenderProfileKey
from toolsv2.visual_profiles import COMPOSITION_MAX_LIGHT, COMPOSITION_OVERWRITE, DEFAULT_PLAIN_JUNCTION_PROFILE_KEY, DEFAULT_ROAD_LAYER_ID, build_v1_plain_junction_visual_profile_catalog


class RenderBehaviorRegistryTests(unittest.TestCase):
    def test_registry_exposes_default_overwrite_and_max_light_rules(self) -> None:
        registry = build_v1_render_behavior_registry()

        self.assertIsNotNone(registry.composition_rule_for(COMPOSITION_OVERWRITE))
        self.assertIsNotNone(registry.composition_rule_for(COMPOSITION_MAX_LIGHT))

    def test_max_light_rule_uses_the_lighter_pixel_values(self) -> None:
        canvas = Image.new("RGBA", (1, 1), (17, 16, 26, 255))
        source = Image.new("RGBA", (1, 1), (44, 45, 57, 255))
        template = LoadedRenderTemplate(
            template_key="tmp",
            kind="sprite_ref",
            width=1,
            height=1,
            image=source,
        )
        instruction = SpriteStampInstruction(
            layer_id="road",
            template_key="tmp",
            anchor_x=0,
            anchor_y=0,
            composition_operator=COMPOSITION_MAX_LIGHT,
        )

        max_light_composition_rule(
            canvas,
            instruction,
            template,
            top_left_x=0,
            top_left_y=0,
        )

        self.assertEqual((44, 45, 57, 255), canvas.getpixel((0, 0)))

    def test_compose_local_block_finalizer_builds_full_width_straight_junction_piece(self) -> None:
        visual_catalog = build_v1_plain_junction_visual_profile_catalog()
        template_loader = build_cached_render_template_loader()
        resolved_object = ResolvedObjectRenderSpec(
            instance_ref="junction_instance",
            profile_key=DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
            anchor_x=2,
            anchor_y=2,
            ports=(
                ResolvedPortRenderSpec(
                    port_id=PortId("west"),
                    pixel_x=0,
                    pixel_y=2,
                    attach_direction="west",
                ),
                ResolvedPortRenderSpec(
                    port_id=PortId("east"),
                    pixel_x=4,
                    pixel_y=2,
                    attach_direction="east",
                ),
            ),
            local_connections=(
                ResolvedLocalConnectionSpec(
                    from_port_id=PortId("west"),
                    to_port_id=PortId("east"),
                    connection_family_key="road_junction_piece",
                ),
            ),
        )

        instructions = compose_local_block_finalizer_rule(
            resolved_object,
            visual_catalog,
            template_loader,
            build_v1_render_behavior_registry().composition_rule_for,
        )

        self.assertEqual(1, len(instructions))
        instruction = instructions[0]
        self.assertIsInstance(instruction, RasterStampInstruction)
        instruction = instruction  # type: ignore[assignment]
        self.assertEqual(DEFAULT_ROAD_LAYER_ID, instruction.layer_id)
        self.assertEqual(
            tuple((17, 16, 26, 255) for _ in range(5)),
            instruction.rgba_rows[1],
        )
        self.assertEqual(
            tuple((44, 45, 57, 255) for _ in range(5)),
            instruction.rgba_rows[2],
        )
        self.assertEqual(
            tuple((17, 16, 26, 255) for _ in range(5)),
            instruction.rgba_rows[3],
        )


if __name__ == "__main__":
    unittest.main()
