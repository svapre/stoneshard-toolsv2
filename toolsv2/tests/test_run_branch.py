from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolsv2.run_branch import run_v1_requirement_tree_json


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

    def test_runner_solves_bundled_magic_mastery_example(self) -> None:
        tree_path = Path(__file__).resolve().parent.parent / "examples" / "vanilla_magic_mastery.json"

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "magic_mastery.png"
            result = run_v1_requirement_tree_json(tree_path, out_path=out_path)

            self.assertEqual("success", result.solve_result.status)
            self.assertTrue(result.output_path.exists())
            self.assertGreater(result.output_path.stat().st_size, 0)
            placement_snapshot = (
                result.solve_result
                .successful_current_grid_result
                .placement_orchestration_result
                .placement_snapshot
            )
            self.assertEqual(
                "x2",
                str(placement_snapshot.assignments["thaumaturgy"].x_rail_id),
            )
            self.assertEqual(
                "x4",
                str(placement_snapshot.assignments["sealReflection"].x_rail_id),
            )
            self.assertEqual(
                "x3",
                str(
                    placement_snapshot.assignments[
                        "node__req__tier4__thaumaturgy__sealReflection"
                    ].x_rail_id
                ),
            )
            self.assertEqual(
                "x2",
                str(placement_snapshot.assignments["sealShackles"].x_rail_id),
            )
            self.assertEqual(
                "x4",
                str(placement_snapshot.assignments["magicLore"].x_rail_id),
            )


if __name__ == "__main__":
    unittest.main()
