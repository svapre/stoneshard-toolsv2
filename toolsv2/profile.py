"""Frozen logical profile and grid construction rules.

This module implements only the frozen profile behavior from
``solver_rules.md``:

- default logical x rails are an ordered family
- the base y grid starts with authored tier rails only
- extra y rails are added through explicit profile-band input
- the first extra rail in a band is the midpoint
- multiple dynamic rails in a band are rebalanced to equal spacing
- authored rails do not move

This module must not assume:

- which band should be expanded next
- how dynamic rail identities should be ordered
- any logical-to-pixel mapping details
- any placement, screening, routing, or refinement behavior

Current temporary open-item workaround:

- The caller supplies dynamic-rail ordering for one band explicitly.
- That caller-supplied ordering is not a finalized solver design.
- It exists only so the frozen midpoint/equal-spacing rule can be applied
  without inventing an unfrozen ordering policy.
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


def rebalance_band_dynamic_y_rails(
    active_grid: ActiveGridState,
    band_id: str | BandId,
    ordered_dynamic_rail_ids: Sequence[str | LogicalYRailId],
) -> ActiveGridState:
    """Apply the frozen generic extra-y-rail rule to one band.

    The caller must supply the full ordered dynamic rail id list for the target
    band as a temporary open-item workaround. This is not a finalized solver
    design. This function does not infer band-selection policy or dynamic rail
    ordering policy because those details are not frozen.
    """

    target_band_id = BandId(str(band_id))
    band_lookup = {band.band_id: band for band in active_grid.y_bands}
    if target_band_id not in band_lookup:
        raise KeyError(f"Unknown band_id: {target_band_id}")

    target_band = band_lookup[target_band_id]
    ordered_dynamic_ids = tuple(
        _coerce_y_rail_id(rail_id)
        for rail_id in ordered_dynamic_rail_ids
    )

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
            logical_rank=upper_authored.logical_rank + (span * Fraction(index, len(ordered_dynamic_ids) + 1)),
            kind="dynamic",
            band_id=target_band_id,
        )
        for index, rail_id in enumerate(ordered_dynamic_ids, start=1)
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
