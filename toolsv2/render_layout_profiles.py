"""Data-only render-layout profiles for concrete pixel mapping and canvas setup.

This module keeps render-space canvas size, default background ownership, and
logical-rail pixel placement data outside the generic renderer core.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


V1_VANILLA_RENDER_LAYOUT_PROFILE_ID = "vanilla_render_layout"


@dataclass(frozen=True, slots=True)
class RenderLayoutProfile:
    """Data-only render-layout preset for one family of rendered graphs."""

    profile_id: str
    canvas_width: int
    canvas_height: int
    default_background_asset_ref: str | None
    x_pixels_by_order: tuple[int, ...]
    authored_tier_y_pixels_by_tier_count: Mapping[int, tuple[int, ...]]
    band_offsets_by_dynamic_rail_count: Mapping[int, tuple[int, ...]]

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("RenderLayoutProfile.profile_id must not be empty")
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            raise ValueError("RenderLayoutProfile canvas dimensions must be positive")
        if not self.x_pixels_by_order:
            raise ValueError("RenderLayoutProfile.x_pixels_by_order must not be empty")
        if len(self.x_pixels_by_order) != len(set(self.x_pixels_by_order)):
            raise ValueError("RenderLayoutProfile.x_pixels_by_order must be unique")
        object.__setattr__(
            self,
            "authored_tier_y_pixels_by_tier_count",
            MappingProxyType(
                {
                    int(count): tuple(int(pixel) for pixel in pixels)
                    for count, pixels in self.authored_tier_y_pixels_by_tier_count.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "band_offsets_by_dynamic_rail_count",
            MappingProxyType(
                {
                    int(count): tuple(int(offset) for offset in offsets)
                    for count, offsets in self.band_offsets_by_dynamic_rail_count.items()
                }
            ),
        )
        for count, pixels in self.authored_tier_y_pixels_by_tier_count.items():
            if count <= 0:
                raise ValueError("Authored tier-count keys must be positive")
            if len(pixels) != count:
                raise ValueError("Authored tier pixel rows must match the tier-count key")
            if len(pixels) != len(set(pixels)):
                raise ValueError("Authored tier y pixels must be unique within one tier-count family")
        for count, offsets in self.band_offsets_by_dynamic_rail_count.items():
            if count <= 0:
                raise ValueError("Dynamic rail-count keys must be positive")
            if len(offsets) != count:
                raise ValueError("Band offsets must match the dynamic rail-count key")
            if tuple(offsets) != tuple(sorted(offsets)):
                raise ValueError("Band offsets must be sorted")


def build_v1_vanilla_render_layout_profile() -> RenderLayoutProfile:
    """Return the explicit current vanilla/default render-layout preset."""

    return RenderLayoutProfile(
        profile_id=V1_VANILLA_RENDER_LAYOUT_PROFILE_ID,
        canvas_width=163,
        canvas_height=257,
        default_background_asset_ref="art/source/background/base/BASE_BACKGROUND.png",
        x_pixels_by_order=(24, 43, 62, 81, 100, 119, 138),
        authored_tier_y_pixels_by_tier_count={
            2: (44, 234),
            3: (55, 128, 201),
            4: (55, 111, 167, 223),
        },
        band_offsets_by_dynamic_rail_count={
            1: (0,),
            2: (-4, 4),
        },
    )
