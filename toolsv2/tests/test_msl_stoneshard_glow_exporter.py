from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toolsv2.adapters.msl_stoneshard import (
    build_default_point_variable_names,
    build_default_stoneshard_line_variable_names,
    build_stoneshard_other_24_gml,
    write_stoneshard_other_24_gml,
)
from toolsv2.glow import GlowExportManifest, GlowLineAssetSpec, GlowLineSpec, GlowPointSpec


class StoneshardGlowExporterTests(unittest.TestCase):
    def _build_manifest(self) -> GlowExportManifest:
        return GlowExportManifest(
            tree_id="necromancy",
            point_specs=(
                GlowPointSpec(point_id="a1", anchor_x=33, anchor_y=55),
                GlowPointSpec(point_id="b1", anchor_x=81, anchor_y=55),
                GlowPointSpec(
                    point_id="a2",
                    anchor_x=24,
                    anchor_y=118,
                    point_dependency_groups=(("a1",), ("b1",)),
                    line_dependency_groups=(("linebase",),),
                ),
            ),
            line_asset_specs=(
                GlowLineAssetSpec(
                    asset_id="asset_line1",
                    asset_name="spr_tree_line1",
                    origin_x=22,
                    origin_y=28,
                ),
                GlowLineAssetSpec(
                    asset_id="asset_linebase",
                    asset_name="spr_tree_linebase",
                    origin_x=0,
                    origin_y=0,
                ),
            ),
            line_specs=(
                GlowLineSpec(
                    line_id="line1",
                    asset_id="asset_line1",
                    anchor_x=24,
                    anchor_y=70,
                    point_dependency_groups=(("a1",),),
                    line_dependency_groups=(("linebase",),),
                ),
                GlowLineSpec(
                    line_id="linebase",
                    asset_id="asset_linebase",
                    anchor_x=24,
                    anchor_y=70,
                    point_dependency_groups=(("a1",), ("b1",)),
                    line_dependency_groups=(("line1",),),
                ),
            ),
        )

    def test_default_variable_names_are_stable_and_sanitized(self) -> None:
        manifest = GlowExportManifest(
            tree_id="test",
            point_specs=(
                GlowPointSpec(point_id="a-1", anchor_x=0, anchor_y=0),
                GlowPointSpec(point_id="a 1", anchor_x=0, anchor_y=0),
            ),
            line_asset_specs=(
                GlowLineAssetSpec(
                    asset_id="asset_line",
                    asset_name="spr_line",
                    origin_x=0,
                    origin_y=0,
                ),
            ),
            line_specs=(
                GlowLineSpec(line_id="line-1", asset_id="asset_line", anchor_x=0, anchor_y=0),
                GlowLineSpec(line_id="line 1", asset_id="asset_line", anchor_x=0, anchor_y=0),
            ),
        )

        point_names = build_default_point_variable_names(manifest)
        line_names = build_default_stoneshard_line_variable_names(manifest)

        self.assertEqual("_a_1", point_names["a-1"])
        self.assertEqual("_a_1_2", point_names["a 1"])
        self.assertEqual("_line_line_1", line_names["line-1"])
        self.assertEqual("_line_line_1_2", line_names["line 1"])

    def test_other_24_export_renders_lines_and_dependency_calls(self) -> None:
        export = build_stoneshard_other_24_gml(
            self._build_manifest(),
            point_variable_names_by_point_id={
                "a1": "darkbolt",
                "b1": "essence_flux",
                "a2": "death_blessing",
            },
            line_variable_names_by_line_id={
                "line1": "line1",
                "linebase": "linebase",
            },
        )

        self.assertIn('var line1_spr = asset_get_index("spr_tree_line1");', export.gml_text)
        self.assertIn('if (line1_spr == -1) line1_spr = asset_get_index("s_empty");', export.gml_text)
        self.assertIn("sprite_set_offset(line1_spr, 22, 28);", export.gml_text)
        self.assertIn(
            "var line1 = new ctr_SkillLine(connectionsRender, line1_spr, 24, 70);",
            export.gml_text,
        )
        self.assertIn(
            "death_blessing.addConnectedPoints([darkbolt], [essence_flux]);",
            export.gml_text,
        )
        self.assertIn(
            "death_blessing.addConnectedLines([linebase]);",
            export.gml_text,
        )
        self.assertIn(
            "linebase.addConnectedPoints([darkbolt], [essence_flux]);",
            export.gml_text,
        )
        self.assertIn(
            "linebase.addConnectedLines([line1]);",
            export.gml_text,
        )

    def test_write_other_24_gml_writes_file(self) -> None:
        manifest = self._build_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = write_stoneshard_other_24_gml(
                manifest,
                Path(temp_dir) / "Other_24.gml",
            )
            self.assertTrue(out_path.exists())
            self.assertIn(
                "var _line_line1 = new ctr_SkillLine(",
                out_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
