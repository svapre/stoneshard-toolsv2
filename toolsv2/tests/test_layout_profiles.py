from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.layout_profiles import (
    V1_VANILLA_SKILL_TREE_LAYOUT_PROFILE_ID,
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    build_minimum_active_grid_for_layout_profile,
    build_band_expansion_step_for_layout_pattern,
    build_v1_vanilla_skill_tree_layout_profile,
    get_band_layout_pattern,
)


class LayoutProfilesTests(unittest.TestCase):
    def test_vanilla_layout_profile_preserves_seven_x_rails_and_one_gap(self) -> None:
        profile = build_v1_vanilla_skill_tree_layout_profile()

        self.assertEqual(V1_VANILLA_SKILL_TREE_LAYOUT_PROFILE_ID, profile.profile_id)
        self.assertEqual(
            ("x0", "x1", "x2", "x3", "x4", "x5", "x6"),
            tuple(str(rail_id) for rail_id in profile.default_x_rail_ids),
        )
        self.assertEqual(1, profile.minimum_same_row_gap)
        self.assertEqual(
            (
                V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
            ),
            tuple(pattern.pattern_id for pattern in profile.band_layout_patterns),
        )

    def test_minimum_grid_builder_uses_layout_profile_x_rails(self) -> None:
        profile = build_v1_vanilla_skill_tree_layout_profile()

        grid = build_minimum_active_grid_for_layout_profile(
            layout_profile=profile,
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        self.assertEqual(
            tuple(str(rail_id) for rail_id in profile.default_x_rail_ids),
            tuple(str(rail.rail_id) for rail in grid.x_rails),
        )
        self.assertEqual(("tier_0", "tier_1"), tuple(str(rail.rail_id) for rail in grid.y_rails))

    def test_vanilla_four_tier_split_pair_pattern_is_profile_local_data(self) -> None:
        profile = build_v1_vanilla_skill_tree_layout_profile()

        pattern = get_band_layout_pattern(
            profile,
            V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
        )

        self.assertEqual(
            (Fraction(3, 7), Fraction(4, 7)),
            pattern.relative_positions,
        )

    def test_band_expansion_step_builder_uses_profile_pattern_positions(self) -> None:
        profile = build_v1_vanilla_skill_tree_layout_profile()
        grid = build_minimum_active_grid_for_layout_profile(
            layout_profile=profile,
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        step = build_band_expansion_step_for_layout_pattern(
            profile,
            band_id=grid.y_bands[0].band_id,
            pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
            ordered_dynamic_rail_ids=("dyn_mid",),
        )

        self.assertEqual((Fraction(1, 2),), step.relative_positions)


if __name__ == "__main__":
    unittest.main()
