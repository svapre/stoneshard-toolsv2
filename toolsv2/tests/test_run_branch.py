from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolsv2.layout_estimation import (
    V1RuleBasedLayoutDemandEstimator,
    build_same_band_multi_sink_split_pattern_rule,
    build_single_sink_mediated_band_rule,
)
from toolsv2.layout_profiles import (
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    build_v1_vanilla_skill_tree_layout_profile,
)
from toolsv2.run_branch import (
    _build_default_grid_expansion_policy_builder,
    run_v1_requirement_tree_json,
)
from toolsv2.skill_tree_requirements import (
    authored_tier_rail_ids_for_tree,
    compile_v1_skill_tree_to_graph_content,
    load_skill_tree_requirement_spec,
)


class RunBranchTests(unittest.TestCase):
    def _write_tree_json(self, payload: dict) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "tree.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_runner_solves_and_writes_png_for_simple_direct_tree(self) -> None:
        tree_path = self._write_tree_json(
            {
                "tree_id": "simple_direct_tree",
                "background_base": "BASE_BACKGROUND.png",
                "skills": [
                    {
                        "id": "a1",
                        "name": "A1",
                        "tier": 1,
                        "slot": 0,
                        "requires": [],
                    },
                    {
                        "id": "b2",
                        "name": "B2",
                        "tier": 2,
                        "slot": 0,
                        "requires": [["a1"]],
                    },
                ],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "branch.png"
            result = run_v1_requirement_tree_json(tree_path, out_path=out_path)

            self.assertEqual("success", result.solve_result.status)
            self.assertTrue(result.output_path.exists())
            self.assertGreater(result.output_path.stat().st_size, 0)

    def test_default_policy_only_upgrades_demanded_band(self) -> None:
        tree_path = self._write_tree_json(
            {
                "tree_id": "band_target_tree",
                "skills": [
                    {"id": "a1", "name": "A1", "tier": 1, "slot": 0, "requires": []},
                    {"id": "b1", "name": "B1", "tier": 1, "slot": 1, "requires": []},
                    {"id": "x2", "name": "X2", "tier": 2, "slot": 0, "requires": [["a1", "b1"]]},
                    {"id": "y3", "name": "Y3", "tier": 3, "slot": 0, "requires": []},
                ],
            }
        )
        requirement_spec = load_skill_tree_requirement_spec(tree_path)
        compiled = compile_v1_skill_tree_to_graph_content(requirement_spec)
        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
        estimator = V1RuleBasedLayoutDemandEstimator(
            layout_profile=layout_profile,
            authored_tier_rail_ids=authored_tier_rail_ids_for_tree(requirement_spec),
            band_layout_demand_rules=(
                build_single_sink_mediated_band_rule(
                    pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                ),
                build_same_band_multi_sink_split_pattern_rule(
                    split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                ),
            ),
        )
        estimate = estimator(compiled.graph_content)
        policy = _build_default_grid_expansion_policy_builder(layout_profile)(estimate)

        next_grid = policy(estimate.initial_grid)
        self.assertIsNotNone(next_grid)
        assert next_grid is not None
        self.assertEqual(
            (
                "tier_0",
                "dyn::tier_0::tier_1::0",
                "dyn::tier_0::tier_1::1",
                "tier_1",
                "tier_2",
            ),
            tuple(str(rail.rail_id) for rail in next_grid.y_rails),
        )
        self.assertIsNone(policy(next_grid))


if __name__ == "__main__":
    unittest.main()
