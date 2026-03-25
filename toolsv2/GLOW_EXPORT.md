# Glow Export Boundary

This document defines the current glow export ownership split.

## Folder Ownership

- `toolsv2/glow/`
  - generic glow export schema
  - generic JSON serialization
  - section decomposition from solved graphs
  - glow line rasterization
  - no Stoneshard/MSL syntax or packaging rules
- `toolsv2/adapters/msl_stoneshard/`
  - Stoneshard/MSL-specific `Other_24` emission
  - sprite asset-name lookup rules
  - GML variable naming helpers
  - clean mod-workspace export helpers

## Generic Manifest

The generic glow manifest is `GlowExportManifest` in `toolsv2/glow/contracts.py`.

It contains:
- `tree_id`
- optional `background_png_path`
- `GlowPointSpec`
- `GlowLineAssetSpec`
- `GlowLineSpec`

The current end-to-end bundle builder is:
- `toolsv2/glow/export.py`

The current CLI entrypoint is:
- `toolsv2/run_glow.py`

### `GlowPointSpec`

Carries:
- `point_id`
- `anchor_x`
- `anchor_y`
- `point_dependency_groups`
- `line_dependency_groups`
- optional `display_name`

### `GlowLineAssetSpec`

Carries:
- `asset_id`
- `asset_name`
- `origin_x`
- `origin_y`
- optional `png_path`

### `GlowLineSpec`

Carries:
- `line_id`
- `asset_id`
- `anchor_x`
- `anchor_y`
- `draw_knot`
- `point_dependency_groups`
- `line_dependency_groups`

## Dependency Semantics

Dependency groups use OR-of-AND:
- each group is one OR alternative
- ids inside one group are AND-required together

Point and line dependencies are stored separately because Stoneshard runtime wiring does the same through:
- `addConnectedPoints(...)`
- `addConnectedLines(...)`

## Stoneshard Adapter

`toolsv2/adapters/msl_stoneshard/glow_exporter.py` converts the generic manifest into:
- `ctr_SkillLine` constructor lines
- `addConnectedPoints(...)`
- `addConnectedLines(...)`

It does not infer solver state, route geometry, or line decomposition. It only consumes the finalized manifest.

`toolsv2/adapters/msl_stoneshard/mod_export.py` then adds the mod-source packaging layer:
- `ctr_SkillPoint` constructor emission from a content-side point binding config
- branch sprite placement into `Sprites/`
- glow line sprite placement into `Sprites/`
- final `Codes/...Other_24.gml` writing
- provenance output into `Generated/toolsv2/<project>/`
- optional clean-workspace scaffolding from an existing noisy mod folder

## Current Section Builder Rule

The current v1 section builder:
- starts from successful solved route plans
- groups routed arcs by identical activation-group signatures
- keeps shared common/fanout sections when geometry is genuinely shared
- duplicates terminal OR-only sink-approach arcs back into their incoming sections instead of emitting a separate shared sink section

That matches the current Magic Mastery-style vanilla line decomposition more closely than a raw geometric shared-arc grouping.

## Why This Split Exists

The solver and generic renderer should not need code changes when:
- the mod changes asset naming
- `Other_24` formatting changes
- another consumer wants non-Stoneshard packaging

Only the adapter layer should change in those cases.

## Necromancy vs Ricochet

Necromancy already follows the cleaner Stoneshard pattern:
- named branch sprite asset
- named glow line sprite assets
- `Other_24` built from named `ctr_SkillLine` assets

Ricochet originally diverged by hardcoding raw sprite ids in `Other_24`.

The clean export path now makes Ricochet follow the Necromancy-style packaging model:
- generated named line assets in `Sprites/`
- generated named branch asset in `Sprites/`
- generated `Other_24` that uses `asset_get_index(...)` and grouped dependencies
- no solver or generic glow-core changes required for the mod-specific packaging

## Clean Workspace Rule

The adapter now supports one clean editable mod workspace layout:

- root:
  - `<ModName>.cs`
  - `<ModName>.csproj`
  - `icon.png`
- `Codes/`
- `Sprites/`
- `Generated/toolsv2/<project>/`

That keeps everything needed for game build/use in one folder without copying old scratch docs, old generator inputs, or legacy validation folders into the working mod workspace.
