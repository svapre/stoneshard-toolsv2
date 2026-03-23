from __future__ import annotations

import unittest
from fractions import Fraction

from toolsv2.routing_policy import (
    disallows_upward_vertical_movement,
    is_move_direction_allowed,
    is_transition_policy_legal,
    validate_adjacent_transition,
)
from toolsv2.solver_types import (
    ActiveGridState,
    Junction,
    LogicalXRail,
    LogicalXRailId,
    LogicalYRail,
    LogicalYRailId,
    RoutingPolicy,
)


def _build_grid() -> ActiveGridState:
    return ActiveGridState(
        x_rails=(
            LogicalXRail(rail_id=LogicalXRailId("x0"), order=0),
            LogicalXRail(rail_id=LogicalXRailId("x1"), order=1),
            LogicalXRail(rail_id=LogicalXRailId("x2"), order=2),
        ),
        y_rails=(
            LogicalYRail(
                rail_id=LogicalYRailId("y0"),
                logical_rank=Fraction(0, 1),
                kind="authored",
                authored_tier_index=0,
            ),
            LogicalYRail(
                rail_id=LogicalYRailId("y1"),
                logical_rank=Fraction(1, 1),
                kind="authored",
                authored_tier_index=1,
            ),
            LogicalYRail(
                rail_id=LogicalYRailId("y2"),
                logical_rank=Fraction(2, 1),
                kind="authored",
                authored_tier_index=2,
            ),
        ),
        y_bands=(),
    )


def _policy(
    *,
    north: bool,
    south: bool,
    east: bool,
    west: bool,
) -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="movement_policy",
        rule_values=(
            ("allow_move_north", north),
            ("allow_move_south", south),
            ("allow_move_east", east),
            ("allow_move_west", west),
        ),
    )


class RoutingPolicyTests(unittest.TestCase):
    def test_validate_adjacent_transition_returns_direction(self) -> None:
        grid = _build_grid()
        direction = validate_adjacent_transition(
            grid,
            Junction(LogicalXRailId("x0"), LogicalYRailId("y1")),
            Junction(LogicalXRailId("x1"), LogicalYRailId("y1")),
        )

        self.assertEqual("east", direction)

    def test_directional_moves_follow_policy_data(self) -> None:
        policy = _policy(north=False, south=True, east=True, west=False)

        self.assertTrue(is_move_direction_allowed(policy, "south"))
        self.assertTrue(is_move_direction_allowed(policy, "east"))
        self.assertFalse(is_move_direction_allowed(policy, "north"))
        self.assertFalse(is_move_direction_allowed(policy, "west"))

    def test_no_upward_behavior_when_policy_says_so(self) -> None:
        grid = _build_grid()
        policy = _policy(north=False, south=True, east=True, west=True)

        self.assertTrue(disallows_upward_vertical_movement(policy))
        self.assertFalse(
            is_transition_policy_legal(
                policy,
                grid,
                Junction(LogicalXRailId("x1"), LogicalYRailId("y1")),
                Junction(LogicalXRailId("x1"), LogicalYRailId("y0")),
            )
        )

    def test_upward_move_is_not_blocked_when_policy_allows_it(self) -> None:
        grid = _build_grid()
        policy = _policy(north=True, south=True, east=True, west=True)

        self.assertFalse(disallows_upward_vertical_movement(policy))
        self.assertTrue(
            is_transition_policy_legal(
                policy,
                grid,
                Junction(LogicalXRailId("x1"), LogicalYRailId("y1")),
                Junction(LogicalXRailId("x1"), LogicalYRailId("y0")),
            )
        )

    def test_non_adjacent_transitions_are_rejected_regardless_of_policy(self) -> None:
        grid = _build_grid()
        policy = _policy(north=True, south=True, east=True, west=True)

        with self.assertRaises(ValueError):
            validate_adjacent_transition(
                grid,
                Junction(LogicalXRailId("x0"), LogicalYRailId("y0")),
                Junction(LogicalXRailId("x2"), LogicalYRailId("y0")),
            )

        with self.assertRaises(ValueError):
            is_transition_policy_legal(
                policy,
                grid,
                Junction(LogicalXRailId("x0"), LogicalYRailId("y0")),
                Junction(LogicalXRailId("x1"), LogicalYRailId("y1")),
            )

    def test_missing_direction_rule_fails_loudly(self) -> None:
        policy = RoutingPolicy(
            policy_id="incomplete_policy",
            rule_values=(
                ("allow_move_north", False),
                ("allow_move_south", True),
            ),
        )

        with self.assertRaises(NotImplementedError):
            is_move_direction_allowed(policy, "east")


if __name__ == "__main__":
    unittest.main()

