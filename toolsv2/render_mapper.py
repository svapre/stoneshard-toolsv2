"""Concrete logical-to-render mapper implementations."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.render_layout_profiles import (
    RenderLayoutProfile,
    build_v1_vanilla_render_layout_profile,
)
from toolsv2.solver_common import (
    ActiveGridState,
    LogicalXRailId,
    LogicalYRail,
    LogicalYRailId,
)
from toolsv2.visual_profiles import LogicalToRenderMapper


@dataclass(frozen=True, slots=True)
class StaticRailPixelMapper(LogicalToRenderMapper):
    """Immutable explicit logical-rail -> pixel mapper."""

    x_pixels_by_rail_id: Mapping[LogicalXRailId, int]
    y_pixels_by_rail_id: Mapping[LogicalYRailId, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "x_pixels_by_rail_id",
            MappingProxyType(dict(self.x_pixels_by_rail_id)),
        )
        object.__setattr__(
            self,
            "y_pixels_by_rail_id",
            MappingProxyType(dict(self.y_pixels_by_rail_id)),
        )

    def x_pixel_for(self, rail_id: LogicalXRailId) -> int:
        try:
            return self.x_pixels_by_rail_id[rail_id]
        except KeyError as exc:
            raise KeyError(f"Unknown x rail id for render mapping: {rail_id}") from exc

    def y_pixel_for(self, rail_id: LogicalYRailId) -> int:
        try:
            return self.y_pixels_by_rail_id[rail_id]
        except KeyError as exc:
            raise KeyError(f"Unknown y rail id for render mapping: {rail_id}") from exc


def _band_dynamic_rails(
    active_grid: ActiveGridState,
    *,
    band_id,
) -> tuple[LogicalYRail, ...]:
    return tuple(
        sorted(
            (
                rail
                for rail in active_grid.y_rails
                if rail.kind == "dynamic" and rail.band_id == band_id
            ),
            key=lambda rail: rail.logical_rank,
        )
    )


def build_static_rail_pixel_mapper(
    active_grid: ActiveGridState,
    render_layout_profile: RenderLayoutProfile,
) -> StaticRailPixelMapper:
    """Build one explicit mapper from the active grid and render-layout data."""

    x_rails = tuple(sorted(active_grid.x_rails, key=lambda rail: rail.order))
    if len(x_rails) > len(render_layout_profile.x_pixels_by_order):
        raise NotImplementedError(
            "Current render layout profile does not supply enough x pixel positions"
        )

    x_pixels_by_rail_id = {
        rail.rail_id: render_layout_profile.x_pixels_by_order[rail.order]
        for rail in x_rails
    }

    authored_y_rails = tuple(
        sorted(
            (rail for rail in active_grid.y_rails if rail.kind == "authored"),
            key=lambda rail: rail.authored_tier_index if rail.authored_tier_index is not None else -1,
        )
    )
    authored_count = len(authored_y_rails)
    try:
        authored_pixels = render_layout_profile.authored_tier_y_pixels_by_tier_count[authored_count]
    except KeyError as exc:
        raise NotImplementedError(
            f"Current render layout profile does not support {authored_count} authored tiers"
        ) from exc

    y_pixels_by_rail_id: dict[LogicalYRailId, int] = {
        rail.rail_id: authored_pixels[index]
        for index, rail in enumerate(authored_y_rails)
    }
    authored_pixel_by_id = {
        rail.rail_id: authored_pixels[index]
        for index, rail in enumerate(authored_y_rails)
    }

    band_lookup = {band.band_id: band for band in active_grid.y_bands}
    for band in active_grid.y_bands:
        dynamic_rails = _band_dynamic_rails(active_grid, band_id=band.band_id)
        if not dynamic_rails:
            continue
        dynamic_count = len(dynamic_rails)
        try:
            offsets = render_layout_profile.band_offsets_by_dynamic_rail_count[dynamic_count]
        except KeyError as exc:
            raise NotImplementedError(
                f"Current render layout profile does not support {dynamic_count} dynamic rails in one band"
            ) from exc
        if len(band.dynamic_rail_ids) != dynamic_count:
            raise ValueError("Band dynamic rail count does not match active-grid dynamic rails")
        upper_y = authored_pixel_by_id[band.upper_authored_rail_id]
        lower_y = authored_pixel_by_id[band.lower_authored_rail_id]
        midpoint_y = (upper_y + lower_y) // 2
        for rail, offset in zip(dynamic_rails, offsets):
            y_pixels_by_rail_id[rail.rail_id] = midpoint_y + offset

    for rail in active_grid.y_rails:
        if rail.rail_id not in y_pixels_by_rail_id:
            if rail.kind == "dynamic" and rail.band_id in band_lookup:
                raise ValueError(f"Dynamic y rail {rail.rail_id!r} did not receive a pixel mapping")
            raise ValueError(f"Y rail {rail.rail_id!r} did not receive a pixel mapping")

    return StaticRailPixelMapper(
        x_pixels_by_rail_id=x_pixels_by_rail_id,
        y_pixels_by_rail_id=y_pixels_by_rail_id,
    )


def build_v1_vanilla_render_mapper(active_grid: ActiveGridState) -> StaticRailPixelMapper:
    """Build the current vanilla/default mapper for one active grid."""

    return build_static_rail_pixel_mapper(
        active_grid=active_grid,
        render_layout_profile=build_v1_vanilla_render_layout_profile(),
    )
