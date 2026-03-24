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


if __name__ == "__main__":
    unittest.main()
