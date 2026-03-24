from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.profile import apply_band_dynamic_y_rail_layout, build_minimum_active_grid
from toolsv2.render_layout_profiles import build_v1_vanilla_render_layout_profile
from toolsv2.render_mapper import (
    build_static_rail_pixel_mapper,
    build_v1_vanilla_render_mapper,
)


class RenderMapperTests(unittest.TestCase):
    def test_vanilla_mapper_maps_default_x_rails_and_three_authored_tiers(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )

        mapper = build_v1_vanilla_render_mapper(active_grid)

        self.assertEqual(24, mapper.x_pixel_for("x0"))
        self.assertEqual(81, mapper.x_pixel_for("x3"))
        self.assertEqual(138, mapper.x_pixel_for("x6"))
        self.assertEqual(55, mapper.y_pixel_for("tier_0"))
        self.assertEqual(128, mapper.y_pixel_for("tier_1"))
        self.assertEqual(201, mapper.y_pixel_for("tier_2"))

    def test_mapper_places_single_dynamic_rail_on_band_midpoint(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2"),
        )
        active_grid = apply_band_dynamic_y_rail_layout(
            active_grid,
            band_id="band::tier_0::tier_1",
            ordered_dynamic_rail_ids=("dyn_0",),
            ordered_relative_positions=(Fraction(1, 2),),
        )

        mapper = build_v1_vanilla_render_mapper(active_grid)

        self.assertEqual(91, mapper.y_pixel_for("dyn_0"))

    def test_mapper_places_split_pair_at_profile_owned_offsets(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2", "tier_3"),
        )
        active_grid = apply_band_dynamic_y_rail_layout(
            active_grid,
            band_id="band::tier_0::tier_1",
            ordered_dynamic_rail_ids=("dyn_left", "dyn_right"),
            ordered_relative_positions=(Fraction(3, 7), Fraction(4, 7)),
        )

        mapper = build_v1_vanilla_render_mapper(active_grid)

        self.assertEqual(79, mapper.y_pixel_for("dyn_left"))
        self.assertEqual(87, mapper.y_pixel_for("dyn_right"))

    def test_mapper_supports_two_tier_render_layout(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        mapper = build_static_rail_pixel_mapper(
            active_grid,
            build_v1_vanilla_render_layout_profile(),
        )

        self.assertEqual(44, mapper.y_pixel_for("tier_0"))
        self.assertEqual(234, mapper.y_pixel_for("tier_1"))

    def test_mapper_fails_loudly_for_unsupported_authored_tier_count(self) -> None:
        active_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1", "tier_2", "tier_3", "tier_4"),
        )

        with self.assertRaises(NotImplementedError):
            build_static_rail_pixel_mapper(
                active_grid,
                build_v1_vanilla_render_layout_profile(),
            )


if __name__ == "__main__":
    unittest.main()
