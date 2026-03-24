"""Reusable layout-demand estimation above graph content and layout profiles.

This module keeps content-to-layout lower-bound reasoning separate from generic
grid construction and from the full solve loop. Estimators are reusable
because they are built from injected rules plus one explicit layout profile and
one explicit authored-tier ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from toolsv2.graph_content import GraphContentModel
from toolsv2.layout_profiles import (
    LayoutProfile,
    build_band_expansion_step_for_layout_pattern,
    build_minimum_active_grid_for_layout_profile,
    get_band_layout_pattern,
)
from toolsv2.production_node_definitions import V1_AND_KNOT_KIND
from toolsv2.profile import apply_band_dynamic_y_rail_layout
from toolsv2.solver_common import ActiveGridState, LogicalYRailId, NodeId


@dataclass(frozen=True, slots=True)
class BandLayoutDemand:
    """One provable lower-bound band-layout demand."""

    upper_authored_tier_rail_id: LogicalYRailId
    lower_authored_tier_rail_id: LogicalYRailId
    pattern_id: str
    ordered_dynamic_rail_ids: tuple[LogicalYRailId, ...]

    def __post_init__(self) -> None:
        if self.upper_authored_tier_rail_id == self.lower_authored_tier_rail_id:
            raise ValueError("BandLayoutDemand requires distinct authored boundary rails")
        if not self.pattern_id:
            raise ValueError("BandLayoutDemand.pattern_id must not be empty")
        if not self.ordered_dynamic_rail_ids:
            raise ValueError("BandLayoutDemand.ordered_dynamic_rail_ids must not be empty")
        if len(self.ordered_dynamic_rail_ids) != len(set(self.ordered_dynamic_rail_ids)):
            raise ValueError("BandLayoutDemand.ordered_dynamic_rail_ids must be unique")


@dataclass(frozen=True, slots=True)
class LayoutDemandEstimate:
    """A reusable estimated starting layout state for one graph content input."""

    authored_tier_rail_ids: tuple[LogicalYRailId, ...]
    initial_grid: ActiveGridState
    band_layout_demands: tuple[BandLayoutDemand, ...] = ()

    def __post_init__(self) -> None:
        if not self.authored_tier_rail_ids:
            raise ValueError("LayoutDemandEstimate.authored_tier_rail_ids must not be empty")
        if len(self.authored_tier_rail_ids) != len(set(self.authored_tier_rail_ids)):
            raise ValueError("LayoutDemandEstimate.authored_tier_rail_ids must be unique")
        authored_grid_ids = tuple(
            rail.rail_id
            for rail in self.initial_grid.y_rails
            if rail.kind == "authored"
        )
        if authored_grid_ids != self.authored_tier_rail_ids:
            raise ValueError(
                "LayoutDemandEstimate.initial_grid authored rails must match authored_tier_rail_ids"
            )


BandLayoutDemandRule = Callable[
    [GraphContentModel, LayoutProfile, tuple[LogicalYRailId, ...]],
    tuple[BandLayoutDemand, ...],
]
LayoutDemandEstimator = Callable[[GraphContentModel], LayoutDemandEstimate]


def _build_band_dynamic_rail_ids(
    upper_authored_tier_rail_id: LogicalYRailId,
    lower_authored_tier_rail_id: LogicalYRailId,
    count: int,
) -> tuple[LogicalYRailId, ...]:
    return tuple(
        LogicalYRailId(
            f"dyn::{upper_authored_tier_rail_id}::{lower_authored_tier_rail_id}::{index}"
        )
        for index in range(count)
    )


def _find_band_id(
    active_grid: ActiveGridState,
    *,
    upper_authored_tier_rail_id: LogicalYRailId,
    lower_authored_tier_rail_id: LogicalYRailId,
):
    for band in active_grid.y_bands:
        if (
            band.upper_authored_rail_id == upper_authored_tier_rail_id
            and band.lower_authored_rail_id == lower_authored_tier_rail_id
        ):
            return band.band_id
    raise KeyError(
        "No active band matches the demanded authored boundary rails"
    )


def _normalize_band_layout_demands(
    band_layout_demands: Iterable[BandLayoutDemand],
) -> tuple[BandLayoutDemand, ...]:
    deduped: dict[tuple[LogicalYRailId, LogicalYRailId], BandLayoutDemand] = {}
    for demand in band_layout_demands:
        key = (
            demand.upper_authored_tier_rail_id,
            demand.lower_authored_tier_rail_id,
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = demand
            continue
        if existing != demand:
            raise ValueError(
                "Conflicting band layout demands for the same authored band are not allowed"
            )
    return tuple(
        deduped[key]
        for key in sorted(deduped, key=lambda item: (str(item[0]), str(item[1])))
    )


def apply_band_layout_demands_to_grid(
    layout_profile: LayoutProfile,
    active_grid: ActiveGridState,
    band_layout_demands: Sequence[BandLayoutDemand],
) -> ActiveGridState:
    """Apply one ordered set of profile-owned band-layout demands to a grid."""

    current_grid = active_grid
    for demand in _normalize_band_layout_demands(band_layout_demands):
        band_id = _find_band_id(
            current_grid,
            upper_authored_tier_rail_id=demand.upper_authored_tier_rail_id,
            lower_authored_tier_rail_id=demand.lower_authored_tier_rail_id,
        )
        expansion_step = build_band_expansion_step_for_layout_pattern(
            layout_profile,
            band_id=band_id,
            pattern_id=demand.pattern_id,
            ordered_dynamic_rail_ids=demand.ordered_dynamic_rail_ids,
        )
        if expansion_step.relative_positions is None:
            raise ValueError("Profile-owned band layout steps must carry relative_positions")
        current_grid = apply_band_dynamic_y_rail_layout(
            current_grid,
            expansion_step.band_id,
            expansion_step.ordered_dynamic_rail_ids,
            expansion_step.relative_positions,
        )
    return current_grid


@dataclass(frozen=True, slots=True)
class V1RuleBasedLayoutDemandEstimator:
    """Reusable layout-demand estimator built from explicit lower-bound rules."""

    layout_profile: LayoutProfile
    authored_tier_rail_ids: tuple[LogicalYRailId, ...]
    band_layout_demand_rules: tuple[BandLayoutDemandRule, ...] = ()

    def __post_init__(self) -> None:
        if not self.authored_tier_rail_ids:
            raise ValueError("authored_tier_rail_ids must not be empty")
        if len(self.authored_tier_rail_ids) != len(set(self.authored_tier_rail_ids)):
            raise ValueError("authored_tier_rail_ids must be unique")

    def __call__(self, content: GraphContentModel) -> LayoutDemandEstimate:
        content_authored_tier_ids = {
            node.authored_tier_y_rail_id
            for node in content.nodes
            if node.authored_tier_y_rail_id is not None
        }
        missing = content_authored_tier_ids.difference(self.authored_tier_rail_ids)
        if missing:
            raise ValueError(
                "Estimator authored_tier_rail_ids must cover all authored tiers used by content"
            )

        base_grid = build_minimum_active_grid_for_layout_profile(
            layout_profile=self.layout_profile,
            authored_tier_rail_ids=self.authored_tier_rail_ids,
        )
        band_layout_demands = _normalize_band_layout_demands(
            demand
            for rule in self.band_layout_demand_rules
            for demand in rule(content, self.layout_profile, self.authored_tier_rail_ids)
        )
        initial_grid = apply_band_layout_demands_to_grid(
            self.layout_profile,
            base_grid,
            band_layout_demands,
        )
        return LayoutDemandEstimate(
            authored_tier_rail_ids=self.authored_tier_rail_ids,
            initial_grid=initial_grid,
            band_layout_demands=band_layout_demands,
        )


def build_same_band_multi_sink_split_pattern_rule(
    *,
    source_node_kind: str = V1_AND_KNOT_KIND,
    split_pattern_id: str,
) -> BandLayoutDemandRule:
    """Build one reusable lower-bound rule for same-band multi-sink fanout."""

    def _rule(
        content: GraphContentModel,
        layout_profile: LayoutProfile,
        authored_tier_rail_ids: tuple[LogicalYRailId, ...],
    ) -> tuple[BandLayoutDemand, ...]:
        order_lookup = {
            rail_id: index
            for index, rail_id in enumerate(authored_tier_rail_ids)
        }
        node_lookup = {
            node.node_id: node
            for node in content.nodes
        }
        outgoing_by_source: dict[NodeId, list] = {}
        incoming_by_sink: dict[NodeId, list] = {}
        for requirement in content.route_requirements:
            outgoing_by_source.setdefault(requirement.source_node_id, []).append(requirement)
            incoming_by_sink.setdefault(requirement.sink_node_id, []).append(requirement)

        pattern = get_band_layout_pattern(
            layout_profile,
            split_pattern_id,
        )
        demands: dict[tuple[LogicalYRailId, LogicalYRailId], BandLayoutDemand] = {}

        for node in content.nodes:
            if node.kind != source_node_kind:
                continue

            outgoing_requirements = outgoing_by_source.get(node.node_id, [])
            if len(outgoing_requirements) < 2:
                continue

            sink_counts_by_tier: dict[LogicalYRailId, int] = {}
            for requirement in outgoing_requirements:
                sink_node = node_lookup[requirement.sink_node_id]
                if sink_node.authored_tier_y_rail_id is None:
                    continue
                sink_counts_by_tier[sink_node.authored_tier_y_rail_id] = (
                    sink_counts_by_tier.get(sink_node.authored_tier_y_rail_id, 0) + 1
                )

            incoming_tiers = {
                node_lookup[requirement.source_node_id].authored_tier_y_rail_id
                for requirement in incoming_by_sink.get(node.node_id, [])
                if node_lookup[requirement.source_node_id].authored_tier_y_rail_id is not None
            }
            if len(incoming_tiers) != 1:
                continue
            upper_tier = next(iter(incoming_tiers))
            if upper_tier not in order_lookup:
                continue

            for lower_tier, sink_count in sink_counts_by_tier.items():
                if sink_count < 2:
                    continue
                if lower_tier not in order_lookup:
                    continue
                if order_lookup[lower_tier] != order_lookup[upper_tier] + 1:
                    continue

                key = (upper_tier, lower_tier)
                demands[key] = BandLayoutDemand(
                    upper_authored_tier_rail_id=upper_tier,
                    lower_authored_tier_rail_id=lower_tier,
                    pattern_id=split_pattern_id,
                    ordered_dynamic_rail_ids=_build_band_dynamic_rail_ids(
                        upper_tier,
                        lower_tier,
                        len(pattern.relative_positions),
                    ),
                )

        return tuple(
            demands[key]
            for key in sorted(demands, key=lambda item: (str(item[0]), str(item[1])))
        )

    return _rule


def build_single_sink_mediated_band_rule(
    *,
    source_node_kind: str = V1_AND_KNOT_KIND,
    pattern_id: str,
) -> BandLayoutDemandRule:
    """Build one reusable lower-bound rule for one mediated-band dynamic node."""

    def _rule(
        content: GraphContentModel,
        layout_profile: LayoutProfile,
        authored_tier_rail_ids: tuple[LogicalYRailId, ...],
    ) -> tuple[BandLayoutDemand, ...]:
        order_lookup = {
            rail_id: index
            for index, rail_id in enumerate(authored_tier_rail_ids)
        }
        node_lookup = {
            node.node_id: node
            for node in content.nodes
        }
        outgoing_by_source: dict[NodeId, list] = {}
        incoming_by_sink: dict[NodeId, list] = {}
        for requirement in content.route_requirements:
            outgoing_by_source.setdefault(requirement.source_node_id, []).append(requirement)
            incoming_by_sink.setdefault(requirement.sink_node_id, []).append(requirement)

        pattern = get_band_layout_pattern(
            layout_profile,
            pattern_id,
        )
        demands: dict[tuple[LogicalYRailId, LogicalYRailId], BandLayoutDemand] = {}

        for node in content.nodes:
            if node.kind != source_node_kind:
                continue

            outgoing_requirements = outgoing_by_source.get(node.node_id, [])
            outgoing_sink_tiers = [
                sink_node.authored_tier_y_rail_id
                for requirement in outgoing_requirements
                for sink_node in (node_lookup[requirement.sink_node_id],)
                if sink_node.authored_tier_y_rail_id is not None
            ]
            if len(outgoing_sink_tiers) != 1:
                continue
            lower_tier = outgoing_sink_tiers[0]

            incoming_tiers = {
                node_lookup[requirement.source_node_id].authored_tier_y_rail_id
                for requirement in incoming_by_sink.get(node.node_id, [])
                if node_lookup[requirement.source_node_id].authored_tier_y_rail_id is not None
            }
            if len(incoming_tiers) != 1:
                continue
            upper_tier = next(iter(incoming_tiers))

            if upper_tier not in order_lookup or lower_tier not in order_lookup:
                continue
            if order_lookup[lower_tier] != order_lookup[upper_tier] + 1:
                continue

            key = (upper_tier, lower_tier)
            demands[key] = BandLayoutDemand(
                upper_authored_tier_rail_id=upper_tier,
                lower_authored_tier_rail_id=lower_tier,
                pattern_id=pattern_id,
                ordered_dynamic_rail_ids=_build_band_dynamic_rail_ids(
                    upper_tier,
                    lower_tier,
                    len(pattern.relative_positions),
                ),
            )

        return tuple(
            demands[key]
            for key in sorted(demands, key=lambda item: (str(item[0]), str(item[1])))
        )

    return _rule
