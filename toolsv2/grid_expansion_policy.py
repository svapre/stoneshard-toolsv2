"""Explicit pure grid-expansion policy contracts for the full solve loop.

This module does not decide solver objectives or infer expansion heuristics.
It only provides a thin policy surface and an explicit profile-rule-based
policy builder that can be injected into the full multi-grid orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Mapping

from toolsv2.profile import apply_band_dynamic_y_rail_layout, rebalance_band_dynamic_y_rails
from toolsv2.solver_common import ActiveGridState, BandId, LogicalYRailId


GridExpansionPolicy = Callable[[ActiveGridState], ActiveGridState | None]


@dataclass(frozen=True, slots=True)
class BandExpansionStep:
    """One explicit profile-rule expansion step for one y band."""

    band_id: BandId
    ordered_dynamic_rail_ids: tuple[LogicalYRailId, ...]
    relative_positions: tuple[Fraction, ...] | None = None

    def __post_init__(self) -> None:
        if not self.ordered_dynamic_rail_ids:
            raise ValueError("BandExpansionStep.ordered_dynamic_rail_ids must not be empty")
        if len(self.ordered_dynamic_rail_ids) != len(set(self.ordered_dynamic_rail_ids)):
            raise ValueError("BandExpansionStep.ordered_dynamic_rail_ids must be unique")
        if self.relative_positions is not None:
            if len(self.relative_positions) != len(self.ordered_dynamic_rail_ids):
                raise ValueError("BandExpansionStep.relative_positions must match ordered_dynamic_rail_ids")
            previous = Fraction(0, 1)
            for position in self.relative_positions:
                if position <= 0 or position >= 1:
                    raise ValueError("BandExpansionStep.relative_positions must lie strictly inside the band")
                if position <= previous:
                    raise ValueError("BandExpansionStep.relative_positions must be strictly increasing")
                previous = position


@dataclass(frozen=True, slots=True)
class ExplicitBandExpansionPolicy:
    """Pure explicit grid-expansion policy over a fixed ordered step list."""

    initial_grid: ActiveGridState
    steps: tuple[BandExpansionStep, ...] = ()
    _transitions: Mapping[ActiveGridState, ActiveGridState] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        transitions: dict[ActiveGridState, ActiveGridState] = {}
        current_grid = self.initial_grid
        seen_grids = {current_grid}

        for step in self.steps:
            if step.relative_positions is None:
                next_grid = rebalance_band_dynamic_y_rails(
                    current_grid,
                    step.band_id,
                    step.ordered_dynamic_rail_ids,
                )
            else:
                next_grid = apply_band_dynamic_y_rail_layout(
                    current_grid,
                    step.band_id,
                    step.ordered_dynamic_rail_ids,
                    step.relative_positions,
                )
            if next_grid == current_grid:
                raise ValueError("ExplicitBandExpansionPolicy step must change the grid")
            if next_grid in seen_grids:
                raise ValueError("ExplicitBandExpansionPolicy must not introduce grid cycles")
            transitions[current_grid] = next_grid
            current_grid = next_grid
            seen_grids.add(current_grid)

        object.__setattr__(self, "_transitions", MappingProxyType(transitions))

    def __call__(self, current_grid: ActiveGridState) -> ActiveGridState | None:
        return self._transitions.get(current_grid)


def build_v1_explicit_band_expansion_policy(
    initial_grid: ActiveGridState,
    steps: tuple[BandExpansionStep, ...] = (),
) -> ExplicitBandExpansionPolicy:
    """Build the current explicit v1 profile-rule expansion policy."""

    return ExplicitBandExpansionPolicy(
        initial_grid=initial_grid,
        steps=steps,
    )
