from __future__ import annotations

import unittest
from pathlib import Path


MODULE_CONTRACTS = Path(__file__).resolve().parents[1] / "module_contracts.md"
REFINEMENT_MODULE = Path(__file__).resolve().parents[1] / "refinement.py"


class ModuleContractsTests(unittest.TestCase):
    def test_phase_sections_exist(self) -> None:
        text = MODULE_CONTRACTS.read_text(encoding="utf-8")

        self.assertIn("## Placement / Domain Phase", text)
        self.assertIn("## Screening Phase", text)
        self.assertIn("## Exact Routing Phase", text)
        self.assertIn("## Refinement Phase", text)

    def test_forbidden_assumptions_are_called_out(self) -> None:
        text = MODULE_CONTRACTS.read_text(encoding="utf-8")

        self.assertIn("No exact routing during domain construction.", text)
        self.assertIn("No guessed geometric heuristics.", text)
        self.assertIn('No hardcoded "no upward movement" in solver core.', text)

    def test_solve_pipeline_section_is_not_duplicated(self) -> None:
        text = MODULE_CONTRACTS.read_text(encoding="utf-8")

        self.assertEqual(1, text.count("### `solve_pipeline.py`"))

    def test_refinement_section_matches_current_file_presence(self) -> None:
        text = MODULE_CONTRACTS.read_text(encoding="utf-8")

        self.assertIn("### `refinement.py`", text)
        if not REFINEMENT_MODULE.exists():
            self.assertIn("- Not implemented yet.", text)


if __name__ == "__main__":
    unittest.main()
