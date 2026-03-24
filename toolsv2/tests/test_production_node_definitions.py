from __future__ import annotations

import unittest

from toolsv2.production_node_definitions import (
    V1_AND_KNOT_BOTTOM_PORT_ID,
    V1_AND_KNOT_KIND,
    V1_AND_KNOT_LEFT_PORT_ID,
    V1_AND_KNOT_RIGHT_PORT_ID,
    V1_AND_KNOT_TOP_PORT_ID,
    V1_SKILL_FRAME_BOTTOM_PORT_ID,
    V1_SKILL_FRAME_KIND,
    V1_SKILL_FRAME_TOP_PORT_ID,
    build_v1_and_knot_node_definition,
    build_v1_production_visual_profile_catalog,
    build_v1_skill_frame_node_definition,
)
from toolsv2.solver_types import NodeId
from toolsv2.visual_profiles import DEFAULT_AND_KNOT_PROFILE_KEY, DEFAULT_SKILL_FRAME_PROFILE_KEY


class ProductionNodeDefinitionsTests(unittest.TestCase):
    def test_skill_frame_definition_uses_frozen_port_ids_and_unbounded_capacity(self) -> None:
        definition = build_v1_skill_frame_node_definition(NodeId("skill_a"))

        self.assertEqual(V1_SKILL_FRAME_KIND, definition.kind)
        self.assertEqual(DEFAULT_SKILL_FRAME_PROFILE_KEY, definition.render_profile.profile_key)
        self.assertEqual(
            (V1_SKILL_FRAME_TOP_PORT_ID, V1_SKILL_FRAME_BOTTOM_PORT_ID),
            tuple(port.port_id for port in definition.ports),
        )
        self.assertEqual(
            ("north", "south"),
            tuple(port.orientation for port in definition.ports),
        )
        self.assertEqual((None, None), tuple(port.capacity for port in definition.ports))

    def test_and_knot_definition_caps_input_ports_and_leaves_output_unbounded(self) -> None:
        definition = build_v1_and_knot_node_definition(NodeId("and_a"))

        self.assertEqual(V1_AND_KNOT_KIND, definition.kind)
        self.assertEqual(DEFAULT_AND_KNOT_PROFILE_KEY, definition.render_profile.profile_key)
        self.assertEqual(
            (
                V1_AND_KNOT_TOP_PORT_ID,
                V1_AND_KNOT_LEFT_PORT_ID,
                V1_AND_KNOT_RIGHT_PORT_ID,
                V1_AND_KNOT_BOTTOM_PORT_ID,
            ),
            tuple(port.port_id for port in definition.ports),
        )
        self.assertEqual(
            ("north", "west", "east", "south"),
            tuple(port.orientation for port in definition.ports),
        )
        self.assertEqual((1, 1, 1, None), tuple(port.capacity for port in definition.ports))

    def test_production_visual_catalog_binds_the_frozen_port_ids(self) -> None:
        catalog = build_v1_production_visual_profile_catalog()
        skill_profile = catalog.build_geometry_profile(DEFAULT_SKILL_FRAME_PROFILE_KEY)
        and_profile = catalog.build_geometry_profile(DEFAULT_AND_KNOT_PROFILE_KEY)

        self.assertEqual(
            (V1_SKILL_FRAME_TOP_PORT_ID, V1_SKILL_FRAME_BOTTOM_PORT_ID),
            tuple(port.port_id for port in skill_profile.ports),
        )
        self.assertEqual(
            (
                V1_AND_KNOT_TOP_PORT_ID,
                V1_AND_KNOT_LEFT_PORT_ID,
                V1_AND_KNOT_RIGHT_PORT_ID,
                V1_AND_KNOT_BOTTOM_PORT_ID,
            ),
            tuple(port.port_id for port in and_profile.ports),
        )


if __name__ == "__main__":
    unittest.main()
