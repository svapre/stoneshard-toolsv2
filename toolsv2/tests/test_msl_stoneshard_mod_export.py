from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from toolsv2.adapters.msl_stoneshard import (
    export_to_stoneshard_mod_workspace,
    load_stoneshard_mod_workspace_config,
    scaffold_clean_stoneshard_mod_workspace,
)


class StoneshardModExportTests(unittest.TestCase):
    def test_loads_bundled_ricochet_config(self) -> None:
        config = load_stoneshard_mod_workspace_config("ricochet")

        self.assertEqual(config.config_id, "ricochet")
        self.assertEqual(config.branch_asset_name, "spr_ricochet_branch")
        self.assertTrue(config.tree_json_path.name.endswith("ricochet.json"))
        self.assertEqual(len(config.point_bindings), 12)
        self.assertEqual(config.point_bindings[0].variable_name, "_deflection")

    def test_exports_ricochet_into_clean_mod_workspace(self) -> None:
        config = load_stoneshard_mod_workspace_config("ricochet")

        with tempfile.TemporaryDirectory() as temp_dir:
            mod_source_dir = Path(temp_dir) / "RicochetModGenerated"
            (mod_source_dir / "Codes").mkdir(parents=True)
            (mod_source_dir / "Sprites").mkdir(parents=True)
            (mod_source_dir / "Codes" / "gml_Object_o_skill_category_ricochet_Create_0.gml").write_text(
                'var _branch = asset_get_index("spr_ricochet_branch");\n',
                encoding="utf-8",
            )

            result = export_to_stoneshard_mod_workspace(
                config,
                mod_source_dir,
                max_placement_seeds=64,
                max_grid_attempts=32,
            )

            self.assertTrue(result.create_0_branch_asset_verified)
            self.assertTrue(result.branch_sprite_path.exists())
            self.assertTrue(result.other_24_path.exists())
            self.assertTrue(result.generated_other_24_path.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertGreater(len(result.line_png_paths), 0)
            self.assertTrue(all(path.exists() for path in result.line_png_paths))

            other_24_text = result.other_24_path.read_text(encoding="utf-8")
            self.assertIn("var _deflection = new ctr_SkillPoint(", other_24_text)
            self.assertIn('asset_get_index("spr_ricochet_line_1")', other_24_text)
            self.assertIn("var _line17 = new ctr_SkillLine(", other_24_text)

    def test_scaffold_creates_minimal_workspace_and_normalizes_csproj(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "SourceMod"
            (source_dir / "Codes").mkdir(parents=True)
            (source_dir / "Sprites").mkdir(parents=True)
            (source_dir / "Tools").mkdir(parents=True)
            (source_dir / "BranchArt").mkdir(parents=True)
            (source_dir / "GlowContracts").mkdir(parents=True)
            (source_dir / "Docs").mkdir(parents=True)

            (source_dir / "RicochetMod.cs").write_text("// code\n", encoding="utf-8")
            (source_dir / "icon.png").write_bytes(b"icon")
            (source_dir / "RicochetMod.csproj").write_text(
                """
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <GlowGeneratorPython>python</GlowGeneratorPython>
    <RicochetGlowContract>GlowContracts\\ricochet_glow_contract.json</RicochetGlowContract>
  </PropertyGroup>
  <Target Name="GenerateRicochetGlowGraph" BeforeTargets="BeforeBuild">
    <Exec Command="python Tools\\branch_glow_topology.py" />
  </Target>
</Project>
""".strip(),
                encoding="utf-8",
            )
            (source_dir / "Codes" / "a.gml").write_text("// gml\n", encoding="utf-8")
            (source_dir / "Sprites" / "spr_skill_test_0.png").write_bytes(b"skill")
            (source_dir / "Sprites" / "spr_test_line_1_0.png").write_bytes(b"line")
            (source_dir / "Docs" / "notes.md").write_text("ignore\n", encoding="utf-8")

            target_dir = Path(temp_dir) / "CleanMod"
            result = scaffold_clean_stoneshard_mod_workspace(source_dir, target_dir)

            self.assertTrue((target_dir / "RicochetMod.cs").exists())
            self.assertTrue((target_dir / "RicochetMod.csproj").exists())
            self.assertTrue((target_dir / "icon.png").exists())
            self.assertTrue((target_dir / "Codes" / "a.gml").exists())
            self.assertTrue((target_dir / "Sprites" / "spr_skill_test_0.png").exists())
            self.assertFalse((target_dir / "Sprites" / "spr_test_line_1_0.png").exists())
            self.assertFalse((target_dir / "Docs").exists())
            self.assertGreater(len(result.copied_paths), 0)

            csproj_text = (target_dir / "RicochetMod.csproj").read_text(encoding="utf-8")
            self.assertNotIn("GlowGeneratorPython", csproj_text)
            self.assertNotIn("branch_glow_topology.py", csproj_text)


if __name__ == "__main__":
    unittest.main()
