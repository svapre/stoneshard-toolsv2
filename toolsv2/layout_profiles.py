"""Data-only layout profiles for reusable grid/spacing presets.

This module keeps named layout presets separate from the generic grid-building
rules in ``profile.py``. A layout profile may supply:

- the default ordered logical x rails for a family of graphs
- the minimum same-row x-rail gap to enforce during placement

Current v1 includes an explicit vanilla skill-tree preset so the previously
hardcoded 7-rail / one-gap assumptions remain available as data rather than
solver-core constants. Band-local dynamic-y-rail layout patterns also live
here so profile-specific rail heuristics do not leak into solver-core modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from toolsv2.grid_expansion_policy import BandExpansionStep
from toolsv2.profile import build_minimum_active_grid
from toolsv2.solver_types import ActiveGridState, BandId, LogicalXRailId, LogicalYRailId


V1_VANILLA_SKILL_TREE_LAYOUT_PROFILE_ID = "vanilla_skill_tree"
V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID = "single_mid"
V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID = "four_tier_split_pair"


@dataclass(frozen=True, slots=True)
class BandLayoutPattern:
    """One profile-local dynamic-y-rail layout pattern for one band."""

    pattern_id: str
    relative_positions: tuple[Fraction, ...]
    supersedes_pattern_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.pattern_id:
            raise ValueError("BandLayoutPattern.pattern_id must not be empty")
        if not self.relative_positions:
            raise ValueError("BandLayoutPattern.relative_positions must not be empty")
        if self.pattern_id in self.supersedes_pattern_ids:
            raise ValueError("BandLayoutPattern must not supersede itself")
        if len(self.supersedes_pattern_ids) != len(set(self.supersedes_pattern_ids)):
            raise ValueError("BandLayoutPattern.supersedes_pattern_ids must be unique")
        previous = Fraction(0, 1)
        for position in self.relative_positions:
            if position <= 0 or position >= 1:
                raise ValueError("BandLayoutPattern positions must lie strictly inside the band")
            if position <= previous:
                raise ValueError("BandLayoutPattern positions must be strictly increasing")
            previous = position


@dataclass(frozen=True, slots=True)
class LayoutProfile:
    """Data-only layout preset for logical-grid construction and spacing."""

    profile_id: str
    default_x_rail_ids: tuple[LogicalXRailId, ...]
    minimum_same_row_gap: int = 1
    band_layout_patterns: tuple[BandLayoutPattern, ...] = ()

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("LayoutProfile.profile_id must not be empty")
        if not self.default_x_rail_ids:
            raise ValueError("LayoutProfile.default_x_rail_ids must not be empty")
        if self.minimum_same_row_gap < 0:
            raise ValueError("LayoutProfile.minimum_same_row_gap must be non-negative")
        pattern_ids = tuple(pattern.pattern_id for pattern in self.band_layout_patterns)
        if len(pattern_ids) != len(set(pattern_ids)):
            raise ValueError("LayoutProfile.band_layout_patterns ids must be unique")


def build_v1_vanilla_skill_tree_layout_profile() -> LayoutProfile:
    """Return the explicit vanilla-inspired current-grid preset."""

    return LayoutProfile(
        profile_id=V1_VANILLA_SKILL_TREE_LAYOUT_PROFILE_ID,
        default_x_rail_ids=tuple(
            LogicalXRailId(f"x{index}")
            for index in range(7)
        ),
        minimum_same_row_gap=1,
        band_layout_patterns=(
            BandLayoutPattern(
                pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                relative_positions=(Fraction(1, 2),),
            ),
            BandLayoutPattern(
                pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                relative_positions=(
                    Fraction(1, 2) - Fraction(1, 14),
                    Fraction(1, 2) + Fraction(1, 14),
                ),
                supersedes_pattern_ids=(V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,),
            ),
        ),
    )


def build_minimum_active_grid_for_layout_profile(
    layout_profile: LayoutProfile,
    authored_tier_rail_ids: Sequence[str | LogicalYRailId],
) -> ActiveGridState:
    """Build the minimum active grid using one explicit layout profile."""

    return build_minimum_active_grid(
        default_x_rail_ids=layout_profile.default_x_rail_ids,
        authored_tier_rail_ids=authored_tier_rail_ids,
    )


def get_band_layout_pattern(
    layout_profile: LayoutProfile,
    pattern_id: str,
) -> BandLayoutPattern:
    """Return one named band-layout pattern from a layout profile."""

    for pattern in layout_profile.band_layout_patterns:
        if pattern.pattern_id == pattern_id:
            return pattern
    raise KeyError(f"Unknown band layout pattern: {pattern_id}")


def band_layout_pattern_supersedes(
    layout_profile: LayoutProfile,
    *,
    stronger_pattern_id: str,
    weaker_pattern_id: str,
) -> bool:
    """Return whether one profile-owned band layout pattern supersedes another."""

    stronger = get_band_layout_pattern(layout_profile, stronger_pattern_id)
    return weaker_pattern_id in stronger.supersedes_pattern_ids


def build_band_expansion_step_for_layout_pattern(
    layout_profile: LayoutProfile,
    *,
    band_id: BandId,
    pattern_id: str,
    ordered_dynamic_rail_ids: Sequence[str | LogicalYRailId],
) -> BandExpansionStep:
    """Build one band-expansion step from profile-local rail layout data."""

    pattern = get_band_layout_pattern(layout_profile, pattern_id)
    dynamic_rail_ids = tuple(LogicalYRailId(str(rail_id)) for rail_id in ordered_dynamic_rail_ids)
    if len(dynamic_rail_ids) != len(pattern.relative_positions):
        raise ValueError("ordered_dynamic_rail_ids must match the pattern's rail count")
    return BandExpansionStep(
        band_id=band_id,
        ordered_dynamic_rail_ids=dynamic_rail_ids,
        relative_positions=pattern.relative_positions,
    )
