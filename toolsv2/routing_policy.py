"""Pure routing-policy queries.

This module stays intentionally narrow. It interprets only a small,
data-driven movement-policy schema inside ``RoutingPolicy.rule_values``:

- ``allow_move_north``: bool
- ``allow_move_south``: bool
- ``allow_move_east``: bool
- ``allow_move_west``: bool

This is sufficient for the currently discussed movement-policy style,
including "no upward movement", without claiming that a broader routing-policy
schema is frozen. If any required movement key is missing, this module raises
``NotImplementedError`` instead of inventing a default.

The module is pure. It must not implement screening, reachability search,
exact routing, or profile-specific behavior.
"""

from __future__ import annotations

from typing import Final

from toolsv2.solver_types import ActiveGridState, CardinalDirection, Junction, RoutingPolicy


_MOVEMENT_RULE_KEYS: Final[dict[CardinalDirection, str]] = {
    "north": "allow_move_north",
    "south": "allow_move_south",
    "east": "allow_move_east",
    "west": "allow_move_west",
}


def _rule_values_lookup(policy: RoutingPolicy) -> dict[str, object]:
    return {key: value for key, value in policy.rule_values}


def _required_bool_rule(policy: RoutingPolicy, key: str) -> bool:
    value = _rule_values_lookup(policy).get(key)
    if value is None:
        raise NotImplementedError(
            f"RoutingPolicy {policy.policy_id!r} is missing required movement rule {key!r}"
        )
    if not isinstance(value, bool):
        raise ValueError(
            f"RoutingPolicy {policy.policy_id!r} rule {key!r} must be a bool"
        )
    return value


def _x_order_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    return {str(rail.rail_id): rail.order for rail in active_grid.x_rails}


def _y_index_lookup(active_grid: ActiveGridState) -> dict[str, int]:
    ordered_y_rails = sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank)
    return {
        str(rail.rail_id): index
        for index, rail in enumerate(ordered_y_rails)
    }


def is_move_direction_allowed(
    policy: RoutingPolicy,
    direction: CardinalDirection,
) -> bool:
    """Return whether one logical move direction is allowed by policy data.

    The current schema is intentionally narrow and requires explicit boolean
    allow/disallow flags per direction.
    """

    return _required_bool_rule(policy, _MOVEMENT_RULE_KEYS[direction])


def disallows_upward_vertical_movement(policy: RoutingPolicy) -> bool:
    """Return whether the policy explicitly disallows upward movement.

    In this module, "upward" is the logical move toward the previous y rail in
    active-grid order, represented by the ``north`` direction.
    """

    return not is_move_direction_allowed(policy, "north")


def validate_adjacent_transition(
    active_grid: ActiveGridState,
    source: Junction,
    target: Junction,
) -> CardinalDirection:
    """Validate that one junction-to-junction move is adjacent and cardinal.

    The returned direction is logical only:

    - ``east``: next x rail in x-order
    - ``west``: previous x rail in x-order
    - ``south``: next y rail in active-grid y order
    - ``north``: previous y rail in active-grid y order
    """

    x_order = _x_order_lookup(active_grid)
    y_index = _y_index_lookup(active_grid)

    source_x = x_order.get(str(source.x_rail_id))
    target_x = x_order.get(str(target.x_rail_id))
    source_y = y_index.get(str(source.y_rail_id))
    target_y = y_index.get(str(target.y_rail_id))

    if source_x is None or target_x is None:
        raise ValueError("Transition references an unknown logical x rail")
    if source_y is None or target_y is None:
        raise ValueError("Transition references an unknown logical y rail")

    x_delta = target_x - source_x
    y_delta = target_y - source_y

    if x_delta == 0 and y_delta == 0:
        raise ValueError("Transition must move to an adjacent junction")
    if x_delta != 0 and y_delta != 0:
        raise ValueError("Diagonal transitions are not adjacent cardinal moves")
    if y_delta == 0:
        if x_delta == 1:
            return "east"
        if x_delta == -1:
            return "west"
        raise ValueError("Horizontal transition must move to an adjacent x rail")
    if x_delta == 0:
        if y_delta == 1:
            return "south"
        if y_delta == -1:
            return "north"
        raise ValueError("Vertical transition must move to an adjacent y rail")

    raise ValueError("Transition must be cardinal and adjacent")


def is_transition_policy_legal(
    policy: RoutingPolicy,
    active_grid: ActiveGridState,
    source: Junction,
    target: Junction,
) -> bool:
    """Return whether an adjacent logical transition is legal under policy."""

    direction = validate_adjacent_transition(active_grid, source, target)
    return is_move_direction_allowed(policy, direction)

