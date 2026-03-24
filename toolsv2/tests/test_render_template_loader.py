from __future__ import annotations

import unittest

from toolsv2.render_template_loader import build_cached_render_template_loader
from toolsv2.source_art_catalog import build_v1_source_render_templates
from toolsv2.visual_profiles import (
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    RenderTransformSpec,
)


class RenderTemplateLoaderTests(unittest.TestCase):
    def test_loader_caches_identical_transformed_templates(self) -> None:
        loader = build_cached_render_template_loader()
        template_spec = next(
            template
            for template in build_v1_source_render_templates()
            if template.template_key == DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY
        )

        first = loader.load(template_spec)
        second = loader.load(template_spec)

        self.assertIs(first, second)

    def test_loader_applies_rotation_to_sprite_templates(self) -> None:
        loader = build_cached_render_template_loader()
        template_spec = next(
            template
            for template in build_v1_source_render_templates()
            if template.template_key == DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY
        )

        rotated = loader.load(
            template_spec,
            RenderTransformSpec(quarter_turns_clockwise=1),
        )

        self.assertEqual((1, 3), (rotated.width, rotated.height))


if __name__ == "__main__":
    unittest.main()
