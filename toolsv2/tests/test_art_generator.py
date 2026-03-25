from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toolsv2.art_generator import (
    generate_v1_art_bundle_json,
    write_standalone_art_bundle,
)


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


class ArtGeneratorTests(unittest.TestCase):
    def test_generate_art_bundle_exposes_intermediate_render_and_glow_artifacts(self) -> None:
        bundle = generate_v1_art_bundle_json(EXAMPLES_DIR / "test_skill_tree.json")

        self.assertEqual("test_skill_tree", bundle.requirement_spec.tree_id)
        self.assertEqual((163, 257), bundle.base_render_result.image.size)
        self.assertEqual((163, 257), bundle.base_render_result.background_image.size)
        self.assertTrue(bundle.base_render_result.layer_images)
        self.assertTrue(bundle.glow_build_result.sections.sections)
        self.assertTrue(bundle.glow_build_result.rasterized_lines)
        self.assertIsNone(bundle.glow_build_result.manifest.background_png_path)
        self.assertTrue(
            all(asset_spec.png_path is None for asset_spec in bundle.glow_build_result.manifest.line_asset_specs)
        )

    def test_write_standalone_art_bundle_writes_branch_layers_and_glow_bundle(self) -> None:
        bundle = generate_v1_art_bundle_json(EXAMPLES_DIR / "test_skill_tree.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            written = write_standalone_art_bundle(bundle, temp_dir)

            self.assertTrue(written.branch_png_path.exists())
            self.assertTrue(written.layer_png_paths)
            self.assertTrue(any(path.name == "background.png" for path in written.layer_png_paths))
            self.assertTrue(written.glow_manifest_path.exists())
            self.assertTrue(written.glow_line_png_paths)
            self.assertTrue(all(path.exists() for path in written.glow_line_png_paths))


if __name__ == "__main__":
    unittest.main()
