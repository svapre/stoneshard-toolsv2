from __future__ import annotations

import unittest
from pathlib import Path

from toolsv2.definitions_loader import load_v1_graph_content
from toolsv2.domain_builder import build_raw_domains
from toolsv2.layout_estimation import (
    V1RuleBasedLayoutDemandEstimator,
    build_adjacent_authored_flow_band_rule,
    build_same_band_multi_sink_split_pattern_rule,
    build_single_sink_mediated_band_rule,
)
from toolsv2.layout_profiles import (
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    build_v1_vanilla_skill_tree_layout_profile,
)
from toolsv2.placement_policy_catalog import (
    V1_SKILL_TREE_ROUTE_GRAPH_SPRING_POLICY_ID,
    resolve_graph_content_candidate_ranker,
)
from toolsv2.placement_solver import _stabilize_domains
from toolsv2.skill_tree_requirements import (
    authored_tier_rail_ids_for_tree,
    compile_v1_skill_tree_to_graph_content,
    load_skill_tree_requirement_spec,
)
from toolsv2.solver_common import NodeId


class PlacementPolicyCatalogTests(unittest.TestCase):
    def test_skill_tree_spring_ranker_prefers_centered_magic_mastery_row_candidate(self) -> None:
        tree_path = Path(__file__).resolve().parent.parent / "examples" / "vanilla_magic_mastery.json"
        tree = load_skill_tree_requirement_spec(tree_path)
        compiled = compile_v1_skill_tree_to_graph_content(tree)
        self.assertEqual(
            V1_SKILL_TREE_ROUTE_GRAPH_SPRING_POLICY_ID,
            compiled.graph_content.placement_candidate_policy_id,
        )
        loaded = load_v1_graph_content(compiled.graph_content)
        ranker = resolve_graph_content_candidate_ranker(compiled.graph_content)
        self.assertIsNotNone(ranker)

        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=layout_profile,
            authored_tier_rail_ids=authored_tier_rail_ids_for_tree(tree),
            band_layout_demand_rules=(
                build_adjacent_authored_flow_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
                build_single_sink_mediated_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
                build_same_band_multi_sink_split_pattern_rule(
                    split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                ),
            ),
        )
        estimate = estimator(compiled.graph_content)
        initial_domains = build_raw_domains(
            active_grid=estimate.initial_grid,
            node_metadata=loaded.node_metadata,
            ordered_same_row_groups=loaded.ordered_same_row_groups,
            minimum_same_row_gap=layout_profile.minimum_same_row_gap,
        )
        stabilized = _stabilize_domains(
            active_grid=estimate.initial_grid,
            routing_policy=loaded.routing_policy,
            domains=initial_domains,
            node_definitions=loaded.node_definitions,
            node_metadata=loaded.node_metadata,
            ordered_same_row_groups=loaded.ordered_same_row_groups,
            port_requirements_by_node_id=loaded.port_requirements_by_node_id,
            minimum_same_row_gap=layout_profile.minimum_same_row_gap,
        )

        magic_lore_domain = stabilized.domains[NodeId("magicLore")]
        ordered = ranker(
            estimate.initial_grid,
            NodeId("magicLore"),
            magic_lore_domain.junctions,
            stabilized.domains,
            layout_profile.minimum_same_row_gap,
        )

        self.assertEqual("x4", str(ordered[0].x_rail_id))


if __name__ == "__main__":
    unittest.main()
