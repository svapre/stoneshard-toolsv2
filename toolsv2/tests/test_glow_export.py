from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toolsv2.glow.export import export_glow_for_successful_run
from toolsv2.glow.section_builder import build_glow_sections_for_successful_run
from toolsv2.run_branch import run_v1_requirement_tree_json


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


class GlowExportTests(unittest.TestCase):
    def test_magic_mastery_section_builder_matches_expected_shape(self) -> None:
        run_result = run_v1_requirement_tree_json(EXAMPLES_DIR / "vanilla_magic_mastery.json")

        section_result = build_glow_sections_for_successful_run(run_result)

        self.assertEqual(12, len(section_result.point_specs))
        self.assertEqual(12, len(section_result.sections))

        activation_groups = {
            section.activation_groups: section
            for section in section_result.sections
        }
        self.assertIn((("sealFinesse", "preciseMovements"),), activation_groups)
        self.assertIn((("thaumaturgy", "sealReflection"),), activation_groups)
        self.assertTrue(activation_groups[(("sealFinesse", "preciseMovements"),)].draw_knot)
        self.assertTrue(activation_groups[(("thaumaturgy", "sealReflection"),)].draw_knot)
        self.assertEqual(
            2,
            sum(1 for section in section_result.sections if section.draw_knot),
        )

    def test_glow_export_writes_manifest_gml_and_line_pngs(self) -> None:
        run_result = run_v1_requirement_tree_json(EXAMPLES_DIR / "vanilla_magic_mastery.json")

        with tempfile.TemporaryDirectory() as temp_dir:
            export_result = export_glow_for_successful_run(
                run_result,
                out_dir=Path(temp_dir) / "magic_mastery_glow",
            )

            self.assertTrue(export_result.manifest_path.exists())
            self.assertTrue(export_result.other_24_path.exists())
            self.assertEqual(12, len(export_result.line_png_paths))
            self.assertTrue(all(path.exists() for path in export_result.line_png_paths))
            self.assertEqual(12, len(export_result.manifest.line_specs))
            self.assertIn(
                "new ctr_SkillLine(",
                export_result.other_24_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
