from __future__ import annotations

import unittest

from toolsv2.source_art_catalog import (
    build_v1_source_art_catalog,
    build_v1_source_render_templates,
)
from toolsv2.visual_profiles import (
    DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
)


class SourceArtCatalogTests(unittest.TestCase):
    def test_source_art_catalog_resolves_grouped_asset_paths(self) -> None:
        catalog = build_v1_source_art_catalog()

        self.assertEqual(
            "art/source/node/skill_frame/FRAME_ROOT.png",
            catalog.asset_ref_for(DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY),
        )
        self.assertEqual(
            "art/source/node/skill_frame/FRAME_ROOT_SHADOW.png",
            catalog.asset_ref_for(DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY),
        )
        self.assertEqual(
            "art/source/node/and_knot/GATE_AND.png",
            catalog.asset_ref_for(DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY),
        )
        self.assertEqual(
            "art/source/connection/external_straight/NONDIR_PORTS_TB.png",
            catalog.asset_ref_for(DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY),
        )
        self.assertEqual(
            "art/source/connection/junction_piece/DIR_PORTS_TR_IN_T_OUT_R.png",
            catalog.asset_ref_for(DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY),
        )

    def test_source_render_templates_are_built_from_the_catalog(self) -> None:
        templates = build_v1_source_render_templates()

        self.assertEqual(
            {
                DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
                DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
                DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
                DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
            },
            {template.template_key for template in templates},
        )
        self.assertTrue(all(template.kind == "sprite_ref" for template in templates))


if __name__ == "__main__":
    unittest.main()
