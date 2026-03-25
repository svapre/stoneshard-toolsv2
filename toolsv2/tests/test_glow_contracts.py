from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolsv2.glow import (
    GlowExportManifest,
    GlowLineAssetSpec,
    GlowLineSpec,
    GlowPointSpec,
    glow_export_manifest_to_dict,
    write_glow_export_manifest_json,
)


class GlowContractsTests(unittest.TestCase):
    def _build_manifest(self) -> GlowExportManifest:
        return GlowExportManifest(
            tree_id="magic_mastery",
            background_png_path="output/magic_mastery.png",
            point_specs=(
                GlowPointSpec(point_id="a1", anchor_x=24, anchor_y=55),
                GlowPointSpec(point_id="b1", anchor_x=62, anchor_y=55),
                GlowPointSpec(
                    point_id="a2",
                    anchor_x=24,
                    anchor_y=111,
                    point_dependency_groups=(("a1", "b1"),),
                    line_dependency_groups=(("line5",),),
                ),
            ),
            line_asset_specs=(
                GlowLineAssetSpec(
                    asset_id="asset_line5",
                    asset_name="s_skill_line_5",
                    origin_x=19,
                    origin_y=13,
                    png_path="sprites/s_skill_line_5_0.png",
                ),
            ),
            line_specs=(
                GlowLineSpec(
                    line_id="line5",
                    asset_id="asset_line5",
                    anchor_x=43,
                    anchor_y=83,
                    draw_knot=True,
                    point_dependency_groups=(("a1", "b1"),),
                ),
            ),
        )

    def test_manifest_validates_cross_references(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown point"):
            GlowExportManifest(
                tree_id="bad",
                point_specs=(
                    GlowPointSpec(
                        point_id="a2",
                        anchor_x=0,
                        anchor_y=0,
                        point_dependency_groups=(("missing",),),
                    ),
                ),
                line_asset_specs=(),
                line_specs=(),
            )

        with self.assertRaisesRegex(ValueError, "unknown asset"):
            GlowExportManifest(
                tree_id="bad",
                point_specs=(GlowPointSpec(point_id="a1", anchor_x=0, anchor_y=0),),
                line_asset_specs=(),
                line_specs=(
                    GlowLineSpec(
                        line_id="line1",
                        asset_id="missing_asset",
                        anchor_x=0,
                        anchor_y=0,
                    ),
                ),
            )

    def test_manifest_to_dict_is_json_friendly(self) -> None:
        payload = glow_export_manifest_to_dict(self._build_manifest())

        self.assertEqual("magic_mastery", payload["tree_id"])
        self.assertEqual([["a1", "b1"]], payload["point_specs"][2]["point_dependency_groups"])
        self.assertEqual("s_skill_line_5", payload["line_asset_specs"][0]["asset_name"])
        self.assertEqual(True, payload["line_specs"][0]["draw_knot"])
        json.dumps(payload)

    def test_write_manifest_json_writes_expected_file(self) -> None:
        manifest = self._build_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = write_glow_export_manifest_json(
                manifest,
                Path(temp_dir) / "glow_manifest.json",
            )

            self.assertTrue(out_path.exists())
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual("magic_mastery", payload["tree_id"])


if __name__ == "__main__":
    unittest.main()
