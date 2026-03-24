from __future__ import annotations

import unittest

from toolsv2.production_family_catalog import (
    V1_AND_KNOT_KIND,
    V1_SKILL_FRAME_KIND,
    build_v1_production_node_family_catalog,
)
from toolsv2.production_visual_catalog import (
    build_v1_production_visual_family_catalog,
    build_v1_production_visual_profile_catalog,
)
from toolsv2.solver_common import NodeId
from toolsv2.visual_profiles import (
    DEFAULT_AND_KNOT_PROFILE_KEY,
    DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
    DEFAULT_SKILL_FRAME_PROFILE_KEY,
)


class ProductionCatalogTests(unittest.TestCase):
    def test_production_node_family_catalog_builds_canonical_definitions(self) -> None:
        family_catalog = build_v1_production_node_family_catalog()

        skill_definition = family_catalog.family_spec(V1_SKILL_FRAME_KIND).build_node_definition(
            NodeId("skill_a")
        )
        and_definition = family_catalog.family_spec(V1_AND_KNOT_KIND).build_node_definition(
            NodeId("and_a")
        )

        self.assertEqual(V1_SKILL_FRAME_KIND, skill_definition.kind)
        self.assertEqual(V1_AND_KNOT_KIND, and_definition.kind)
        self.assertEqual((None, None), tuple(port.capacity for port in skill_definition.ports))
        self.assertEqual((1, 1, 1, None), tuple(port.capacity for port in and_definition.ports))

    def test_production_node_family_catalog_rejects_unknown_kind(self) -> None:
        family_catalog = build_v1_production_node_family_catalog()

        with self.assertRaises(KeyError):
            family_catalog.family_spec("mystery_kind")

    def test_production_visual_family_catalog_registers_current_node_profiles(self) -> None:
        visual_family_catalog = build_v1_production_visual_family_catalog()

        self.assertIsNotNone(visual_family_catalog.family_spec(DEFAULT_SKILL_FRAME_PROFILE_KEY))
        self.assertIsNotNone(visual_family_catalog.family_spec(DEFAULT_AND_KNOT_PROFILE_KEY))

    def test_production_visual_profile_catalog_merges_junction_and_registered_families(self) -> None:
        catalog = build_v1_production_visual_profile_catalog()

        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY))
        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_SKILL_FRAME_PROFILE_KEY))
        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_AND_KNOT_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_SKILL_FRAME_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_AND_KNOT_PROFILE_KEY))


if __name__ == "__main__":
    unittest.main()
