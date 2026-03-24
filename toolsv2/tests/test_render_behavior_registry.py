from __future__ import annotations

import unittest

from PIL import Image

from toolsv2.render_behavior_registry import (
    build_v1_render_behavior_registry,
    max_light_composition_rule,
)
from toolsv2.render_contracts import SpriteStampInstruction
from toolsv2.render_template_loader import LoadedRenderTemplate
from toolsv2.visual_profiles import COMPOSITION_MAX_LIGHT, COMPOSITION_OVERWRITE


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


if __name__ == "__main__":
    unittest.main()
