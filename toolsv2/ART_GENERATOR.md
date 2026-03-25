## Art Generator

`toolsv2.art_generator` is the standalone art boundary for skill-tree outputs.

It is intentionally generic:
- input: requirement spec JSON or `SkillTreeRequirementSpec`
- output:
  - solved logical graph artifacts
  - base/background render
  - per-layer render canvases
  - glow sections
  - rasterized glow line sprites
  - generic glow manifest

It intentionally does not emit:
- Stoneshard `Other_24` GML
- MSL packaging
- mod workspace layout rules

Those stay in adapter modules such as:
- `toolsv2/adapters/msl_stoneshard/`

### Main API

- `generate_v1_art_bundle(...)`
- `generate_v1_art_bundle_json(...)`
- `write_standalone_art_bundle(...)`

### Output Folder Layout

`write_standalone_art_bundle(...)` writes:

- `<out>/<tree_id>.png`
- `<out>/layers/background.png`
- `<out>/layers/<layer_id>.png`
- `<out>/glow/glow_manifest.json`
- `<out>/glow/lines/<asset_name>_0.png`

This makes the final art and the intermediate layers directly inspectable by
other generators or downstream packagers.

### CLI

```powershell
python -m toolsv2.run_art_generator toolsv2/examples/test_branch.json
```

By default this writes to:

`toolsv2/output/<tree_id>_art/`
