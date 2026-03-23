from __future__ import annotations

import unittest
from pathlib import Path


MODULE_CONTRACTS = Path(__file__).resolve().parents[1] / "module_contracts.md"


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


if __name__ == "__main__":
    unittest.main()

