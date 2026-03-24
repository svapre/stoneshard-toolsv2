from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.grid_expansion_policy import (
    BandExpansionStep,
    build_v1_explicit_band_expansion_policy,
)
from toolsv2.profile import build_minimum_active_grid
from toolsv2.solver_types import LogicalYRailId


class GridExpansionPolicyTests(unittest.TestCase):
    def test_explicit_band_policy_advances_through_steps_then_stops(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        policy = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_a"),),
                ),
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_a"), LogicalYRailId("dyn_b")),
                ),
            ),
        )

        first_grid = policy(initial_grid)
        self.assertIsNotNone(first_grid)
        self.assertEqual(
            ("tier_0", "dyn_a", "tier_1"),
            tuple(str(rail.rail_id) for rail in first_grid.y_rails),
        )

        second_grid = policy(first_grid)
        self.assertIsNotNone(second_grid)
        self.assertEqual(
            ("tier_0", "dyn_a", "dyn_b", "tier_1"),
            tuple(str(rail.rail_id) for rail in second_grid.y_rails),
        )
        self.assertIsNone(policy(second_grid))

    def test_explicit_band_policy_rejects_nonchanging_or_cyclic_steps(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )

        with self.assertRaises(ValueError):
            build_v1_explicit_band_expansion_policy(
                initial_grid=initial_grid,
                steps=(
                    BandExpansionStep(
                        band_id=initial_grid.y_bands[0].band_id,
                        ordered_dynamic_rail_ids=(LogicalYRailId("dyn_a"),),
                    ),
                    BandExpansionStep(
                        band_id=initial_grid.y_bands[0].band_id,
                        ordered_dynamic_rail_ids=(LogicalYRailId("dyn_a"),),
                    ),
                ),
            )

    def test_explicit_band_policy_can_use_exact_profile_owned_positions(self) -> None:
        initial_grid = build_minimum_active_grid(
            default_x_rail_ids=("x0",),
            authored_tier_rail_ids=("tier_0", "tier_1"),
        )
        policy = build_v1_explicit_band_expansion_policy(
            initial_grid=initial_grid,
            steps=(
                BandExpansionStep(
                    band_id=initial_grid.y_bands[0].band_id,
                    ordered_dynamic_rail_ids=(LogicalYRailId("dyn_lo"), LogicalYRailId("dyn_hi")),
                    relative_positions=(Fraction(3, 7), Fraction(4, 7)),
                ),
            ),
        )

        next_grid = policy(initial_grid)
        self.assertIsNotNone(next_grid)
        dynamic_ranks = {
            str(rail.rail_id): rail.logical_rank
            for rail in next_grid.y_rails
            if rail.kind == "dynamic"
        }

        self.assertEqual(Fraction(3, 7), dynamic_ranks["dyn_lo"])
        self.assertEqual(Fraction(4, 7), dynamic_ranks["dyn_hi"])


if __name__ == "__main__":
    unittest.main()
