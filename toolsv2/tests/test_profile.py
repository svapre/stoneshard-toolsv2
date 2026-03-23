from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.profile import (
    build_authored_tier_y_rails,
    build_default_x_rails,
    build_minimum_active_grid,
    rebalance_band_dynamic_y_rails,
)


class ProfileTests(unittest.TestCase):
    def test_build_default_x_rails_preserves_input_order(self) -> None:
        rails = build_default_x_rails(("x_left", "x_mid", "x_right"))

        self.assertEqual(("x_left", "x_mid", "x_right"), tuple(str(rail.rail_id) for rail in rails))
        self.assertEqual((0, 1, 2), tuple(rail.order for rail in rails))

    def test_build_authored_tier_y_rails_uses_integral_logical_ranks(self) -> None:
        rails = build_authored_tier_y_rails(("tier_0", "tier_1", "tier_2"))

        self.assertEqual(("authored", "authored", "authored"), tuple(rail.kind for rail in rails))
        self.assertEqual((Fraction(0, 1), Fraction(1, 1), Fraction(2, 1)), tuple(rail.logical_rank for rail in rails))
        self.assertEqual((0, 1, 2), tuple(rail.authored_tier_index for rail in rails))

    def test_first_dynamic_rail_in_band_goes_to_midpoint(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        band_id = grid.y_bands[0].band_id

        expanded = rebalance_band_dynamic_y_rails(grid, band_id, ("dyn_a",))
        dynamic_rail = next(rail for rail in expanded.y_rails if str(rail.rail_id) == "dyn_a")

        self.assertEqual(Fraction(1, 2), dynamic_rail.logical_rank)
        self.assertEqual("dynamic", dynamic_rail.kind)
        self.assertEqual(("dyn_a",), tuple(str(rail_id) for rail_id in expanded.y_bands[0].dynamic_rail_ids))

    def test_multiple_dynamic_rails_in_band_are_rebalanced_to_equal_spacing(self) -> None:
        grid = build_minimum_active_grid(
            default_x_rail_ids=("x0", "x1"),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        band_id = grid.y_bands[0].band_id

        expanded = rebalance_band_dynamic_y_rails(grid, band_id, ("dyn_a", "dyn_b"))
        dynamic_ranks = {
            str(rail.rail_id): rail.logical_rank
            for rail in expanded.y_rails
            if rail.kind == "dynamic"
        }

        self.assertEqual(Fraction(1, 3), dynamic_ranks["dyn_a"])
        self.assertEqual(Fraction(2, 3), dynamic_ranks["dyn_b"])
        self.assertEqual(
            ("tier_0", "dyn_a", "dyn_b", "tier_1"),
            tuple(str(rail.rail_id) for rail in expanded.y_rails),
        )


if __name__ == "__main__":
    unittest.main()

