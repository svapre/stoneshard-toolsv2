from __future__ import annotations

import unittest

from toolsv2.glow.rasterizer import rasterize_glow_section
from toolsv2.glow.section_builder import GlowSection
from toolsv2.solver_common import Junction, LogicalXRailId, LogicalYRailId, PortId, PortRef


def _lit_pixels(image):
    rgba = image.convert("RGBA")
    lit = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            if rgba.getpixel((x, y))[3] != 0:
                lit.append((x, y))
    return tuple(lit)


class GlowRasterizerTests(unittest.TestCase):
    def test_horizontal_straight_section_uses_single_light_core_row(self) -> None:
        source_port = PortRef(owner_ref="source", owner_local_key=PortId("right"))
        sink_port = PortRef(owner_ref="sink", owner_local_key=PortId("left"))
        section = GlowSection(
            section_id="line1",
            arc_keys=frozenset({(source_port, sink_port)}),
            activation_groups=(("source",),),
            line_dependency_groups=(),
            sink_point_ids=(),
            draw_knot=False,
            root_port_refs=(source_port,),
            leaf_port_refs=(sink_port,),
        )

        rasterized = rasterize_glow_section(
            section,
            asset_name="spr_test_line_1",
            port_pixels_by_port_ref={
                source_port: (0, 0),
                sink_port: (4, 0),
            },
        )

        self.assertEqual(
            ((2, 2), (3, 2), (4, 2), (5, 2), (6, 2)),
            _lit_pixels(rasterized.image),
        )

    def test_junction_turn_uses_corner_light_core_shape(self) -> None:
        junction = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("y0"),
        )
        north_port = PortRef(owner_ref=junction, owner_local_key=PortId("north"))
        east_port = PortRef(owner_ref=junction, owner_local_key=PortId("east"))
        south_port = PortRef(owner_ref=junction, owner_local_key=PortId("south"))
        west_port = PortRef(owner_ref=junction, owner_local_key=PortId("west"))
        section = GlowSection(
            section_id="line_corner",
            arc_keys=frozenset({(north_port, east_port)}),
            activation_groups=(("source",),),
            line_dependency_groups=(),
            sink_point_ids=(),
            draw_knot=False,
            root_port_refs=(north_port,),
            leaf_port_refs=(east_port,),
        )

        rasterized = rasterize_glow_section(
            section,
            asset_name="spr_test_line_corner",
            port_pixels_by_port_ref={
                north_port: (10, 8),
                south_port: (10, 12),
                west_port: (8, 10),
                east_port: (12, 10),
            },
        )

        self.assertEqual(
            ((2, 2), (3, 2), (3, 3), (4, 3), (4, 4)),
            _lit_pixels(rasterized.image),
        )

    def test_west_to_south_turn_uses_bottom_left_corner_core_shape(self) -> None:
        junction = Junction(
            x_rail_id=LogicalXRailId("x0"),
            y_rail_id=LogicalYRailId("y0"),
        )
        north_port = PortRef(owner_ref=junction, owner_local_key=PortId("north"))
        east_port = PortRef(owner_ref=junction, owner_local_key=PortId("east"))
        south_port = PortRef(owner_ref=junction, owner_local_key=PortId("south"))
        west_port = PortRef(owner_ref=junction, owner_local_key=PortId("west"))
        section = GlowSection(
            section_id="line_corner_ws",
            arc_keys=frozenset({(west_port, south_port)}),
            activation_groups=(("source",),),
            line_dependency_groups=(),
            sink_point_ids=(),
            draw_knot=False,
            root_port_refs=(west_port,),
            leaf_port_refs=(south_port,),
        )

        rasterized = rasterize_glow_section(
            section,
            asset_name="spr_test_line_corner_ws",
            port_pixels_by_port_ref={
                north_port: (10, 8),
                south_port: (10, 12),
                west_port: (8, 10),
                east_port: (12, 10),
            },
        )

        self.assertEqual(
            ((2, 2), (2, 3), (3, 3), (3, 4), (4, 4)),
            _lit_pixels(rasterized.image),
        )


if __name__ == "__main__":
    unittest.main()
