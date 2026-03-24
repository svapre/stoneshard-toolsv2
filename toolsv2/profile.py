"""Frozen logical profile and grid construction rules.

This module implements only the frozen generic grid-construction behavior from
``solver_rules.md``:

- default logical x rails are an ordered family
- the base y grid starts with authored tier rails only
- extra y rails are added through explicit profile-band input
- exact in-band dynamic-rail layouts may be supplied explicitly
- equal-spacing rebalancing is available as a generic utility for profiles that
  choose that rule
- authored rails do not move

This module must not assume:

- which band should be expanded next
- how dynamic rail identities should be ordered
- any logical-to-pixel mapping details
- any placement, screening, routing, or refinement behavior

Current temporary/open profile-policy boundary:

- The caller supplies band-local dynamic-rail identities explicitly.
- If a profile wants exact in-band positions, the caller supplies those too.
- This module does not infer profile-specific band-layout heuristics.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from toolsv2.solver_types import (
    ActiveGridState,
    BandId,
    LogicalXRail,
    LogicalXRailId,
    LogicalYRail,
    LogicalYRailId,
    YRailBandState,
)
from toolsv2.visual_profiles import LogicalToRenderMapper


LogicalToPixelMapper = LogicalToRenderMapper


def _coerce_x_rail_id(value: str | LogicalXRailId) -> LogicalXRailId:
    return LogicalXRailId(str(value))


def _coerce_y_rail_id(value: str | LogicalYRailId) -> LogicalYRailId:
    return LogicalYRailId(str(value))


def _build_band_id(
    upper_authored_rail_id: LogicalYRailId,
    lower_authored_rail_id: LogicalYRailId,
) -> BandId:
    return BandId(f"band::{upper_authored_rail_id}::{lower_authored_rail_id}")


def _y_rails_sorted(y_rails: Sequence[LogicalYRail]) -> tuple[LogicalYRail, ...]:
    return tuple(sorted(y_rails, key=lambda rail: rail.logical_rank))


def build_default_x_rails(
    ordered_rail_ids: Sequence[str | LogicalXRailId],
) -> tuple[LogicalXRail, ...]:
    """Build the default ordered logical x rail family.

    The input sequence is the source of truth for x-rail order. This function
    does not invent a default count or pixel spacing.
    """

    rail_ids = tuple(_coerce_x_rail_id(rail_id) for rail_id in ordered_rail_ids)
    return tuple(
        LogicalXRail(rail_id=rail_id, order=index)
        for index, rail_id in enumerate(rail_ids)
    )


def build_authored_tier_y_rails(
    ordered_tier_rail_ids: Sequence[str | LogicalYRailId],
) -> tuple[LogicalYRail, ...]:
    """Build authored/static tier rails for the minimum active y grid.

    Authored rails receive integral logical ranks in input order. This module
    does not infer missing tiers or dynamic rails.
    """

    rail_ids = tuple(_coerce_y_rail_id(rail_id) for rail_id in ordered_tier_rail_ids)
    return tuple(
        LogicalYRail(
            rail_id=rail_id,
            logical_rank=Fraction(index, 1),
            kind="authored",
            authored_tier_index=index,
        )
        for index, rail_id in enumerate(rail_ids)
    )


def build_authored_y_bands(
    authored_y_rails: Sequence[LogicalYRail],
) -> tuple[YRailBandState, ...]:
    """Build profile bands between adjacent authored tier rails.

    Band identity is derived from authored boundary rail ids so this function
    does not rely on hidden numbering rules.
    """

    authored = tuple(authored_y_rails)
    for rail in authored:
        if rail.kind != "authored":
            raise ValueError("build_authored_y_bands requires authored y rails only")

    return tuple(
        YRailBandState(
            band_id=_build_band_id(upper.rail_id, lower.rail_id),
            upper_authored_rail_id=upper.rail_id,
            lower_authored_rail_id=lower.rail_id,
        )
        for upper, lower in zip(authored, authored[1:])
    )


def build_minimum_active_grid(
    default_x_rail_ids: Sequence[str | LogicalXRailId],
    authored_tier_rail_ids: Sequence[str | LogicalYRailId],
) -> ActiveGridState:
    """Build the minimum active grid from default x rails and authored tiers."""

    x_rails = build_default_x_rails(default_x_rail_ids)
    authored_y_rails = build_authored_tier_y_rails(authored_tier_rail_ids)
    y_bands = build_authored_y_bands(authored_y_rails)
    return ActiveGridState(
        x_rails=x_rails,
        y_rails=authored_y_rails,
        y_bands=y_bands,
    )


def apply_band_dynamic_y_rail_layout(
    active_grid: ActiveGridState,
    band_id: str | BandId,
    ordered_dynamic_rail_ids: Sequence[str | LogicalYRailId],
    ordered_relative_positions: Sequence[Fraction],
) -> ActiveGridState:
    """Apply one explicit profile-owned dynamic-y-rail layout to one band."""

    target_band_id = BandId(str(band_id))
    band_lookup = {band.band_id: band for band in active_grid.y_bands}
    if target_band_id not in band_lookup:
        raise KeyError(f"Unknown band_id: {target_band_id}")

    target_band = band_lookup[target_band_id]
    ordered_dynamic_ids = tuple(
        _coerce_y_rail_id(rail_id)
        for rail_id in ordered_dynamic_rail_ids
    )
    ordered_positions = tuple(ordered_relative_positions)

    if len(ordered_dynamic_ids) != len(ordered_positions):
        raise ValueError("ordered_dynamic_rail_ids and ordered_relative_positions must match in length")
    if not ordered_dynamic_ids:
        raise ValueError("ordered_dynamic_rail_ids must not be empty")

    previous_position = Fraction(0, 1)
    for position in ordered_positions:
        if position <= 0 or position >= 1:
            raise ValueError("Band rail positions must lie strictly inside the band")
        if position <= previous_position:
            raise ValueError("Band rail positions must be strictly increasing")
        previous_position = position

    upper_authored = next(
        rail for rail in active_grid.y_rails if rail.rail_id == target_band.upper_authored_rail_id
    )
    lower_authored = next(
        rail for rail in active_grid.y_rails if rail.rail_id == target_band.lower_authored_rail_id
    )

    span = lower_authored.logical_rank - upper_authored.logical_rank
    if span <= 0:
        raise ValueError("Band authored rails must have increasing logical_rank")

    new_dynamic_rails = tuple(
        LogicalYRail(
            rail_id=rail_id,
            logical_rank=upper_authored.logical_rank + (span * position),
            kind="dynamic",
            band_id=target_band_id,
        )
        for rail_id, position in zip(ordered_dynamic_ids, ordered_positions)
    )

    existing_target_dynamic_ids = set(target_band.dynamic_rail_ids)
    other_y_rails = tuple(
        rail
        for rail in active_grid.y_rails
        if rail.rail_id not in existing_target_dynamic_ids
    )

    new_y_rails = _y_rails_sorted(other_y_rails + new_dynamic_rails)
    new_y_bands = tuple(
        YRailBandState(
            band_id=band.band_id,
            upper_authored_rail_id=band.upper_authored_rail_id,
            lower_authored_rail_id=band.lower_authored_rail_id,
            dynamic_rail_ids=ordered_dynamic_ids if band.band_id == target_band_id else band.dynamic_rail_ids,
        )
        for band in active_grid.y_bands
    )

    return ActiveGridState(
        x_rails=active_grid.x_rails,
        y_rails=new_y_rails,
        y_bands=new_y_bands,
    )


def rebalance_band_dynamic_y_rails(
    active_grid: ActiveGridState,
    band_id: str | BandId,
    ordered_dynamic_rail_ids: Sequence[str | LogicalYRailId],
) -> ActiveGridState:
    """Apply one generic equal-spacing dynamic-y-rail layout to one band.

    This is a utility for profiles that use the midpoint/equal-spacing rule.
    Profile-specific rail patterns should use ``apply_band_dynamic_y_rail_layout``.
    """

    ordered_dynamic_ids = tuple(
        _coerce_y_rail_id(rail_id)
        for rail_id in ordered_dynamic_rail_ids
    )
    positions = tuple(
        Fraction(index, len(ordered_dynamic_ids) + 1)
        for index in range(1, len(ordered_dynamic_ids) + 1)
    )
    return apply_band_dynamic_y_rail_layout(
        active_grid=active_grid,
        band_id=band_id,
        ordered_dynamic_rail_ids=ordered_dynamic_ids,
        ordered_relative_positions=positions,
    )


def map_logical_grid_to_pixels(
    active_grid: ActiveGridState,
    mapper: LogicalToPixelMapper,
) -> None:
    """Placeholder hook for unfrozen logical-to-pixel mapping behavior.

    TODO: implement once logical-to-pixel mapping details are frozen.
    """

    del active_grid
    del mapper
    raise NotImplementedError(
        "Logical-to-pixel mapping details are open in toolsv2/solver_rules.md"
    )
