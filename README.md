# Stoneshard Toolsv2

Standalone repository for the current `toolsv2` solver, layout, and base-render stack.

This repo intentionally includes only:
- the current `toolsv2` source modules
- the current `toolsv2/tests` suite
- the current contract/design docs inside `toolsv2`
- the current source art primitives, examples, and extractor inputs/reports used by the maintained toolsv2 flow

This repo intentionally excludes:
- legacy prototype code
- logs, caches, generated renders, and extractor build byproducts
- anything outside the current `toolsv2` project boundary

## Project Layout

- `toolsv2/`
  - current solver, layout, and render modules
- `toolsv2/glow/`
  - generic glow export contracts and serialization helpers
- `toolsv2/art_generator.py`
  - standalone branch/glow art generation API with accessible intermediate layers
- `toolsv2/adapters/msl_stoneshard/`
  - Stoneshard/MSL-specific emitters and mod-workspace exporters layered above generic contracts
- `toolsv2/tests/`
  - current unittest coverage
- `toolsv2/art/source/`
  - authored primitive source art grouped by object/family
- `toolsv2/examples/`
  - maintained example requirement specs
- `scripts/`
  - repo-level utilities such as MSL unpacking

The glow export boundary is intentionally split:
- generic manifest/schema stays in `toolsv2/glow`
- game/mod packaging stays in `toolsv2/adapters/msl_stoneshard`

That keeps solver/render core free of Stoneshard-specific file and GML rules.

## Setup

### PowerShell

```powershell
.\scripts\setup.ps1
```

### Bash

```bash
./scripts/setup.sh
```

### Manual

```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

On Unix-like systems, use `.venv/bin/python` instead.

## Run Tests

```bash
python -m unittest discover -s toolsv2/tests -v
```

## Run Example

```bash
python -m toolsv2.run_branch toolsv2/examples/test_branch.json
```

By default this writes the base render to `toolsv2/output/<tree_id>.png`.

The larger bundled smoke example also works:

```bash
python -m toolsv2.run_branch toolsv2/examples/test_skill_tree.json
```

Generate the background plus glow export bundle:

```bash
python -m toolsv2.run_glow toolsv2/examples/vanilla_magic_mastery.json
```

By default this writes:
- background PNG to `toolsv2/output/<tree_id>.png`
- glow bundle to `toolsv2/output/<tree_id>_glow/`

Generate the standalone generic art bundle with intermediate layer PNGs:

```bash
python -m toolsv2.run_art_generator toolsv2/examples/test_branch.json
```

By default this writes:
- branch/background PNG to `toolsv2/output/<tree_id>_art/<tree_id>.png`
- intermediate layer PNGs to `toolsv2/output/<tree_id>_art/layers/`
- generic glow bundle to `toolsv2/output/<tree_id>_art/glow/`

## Glow Export Boundary

The repo now includes the first explicit glow export schema:
- `toolsv2/glow/contracts.py`
- `toolsv2/glow/serialization.py`
- `toolsv2/glow/section_builder.py`
- `toolsv2/glow/rasterizer.py`
- `toolsv2/glow/export.py`

And the first game-specific adapter:
- `toolsv2/adapters/msl_stoneshard/glow_exporter.py`

And the first clean mod-workspace exporter:
- `toolsv2/adapters/msl_stoneshard/mod_export.py`
- bundled project config:
  - `toolsv2/adapters/msl_stoneshard/mod_configs/ricochet.json`

The generic manifest carries:
- point ids and anchors
- line asset ids/names/origins
- line instances with anchors and `draw_knot`
- point and line dependency groups using the same OR-of-AND shape used by Stoneshard runtime wiring

The Stoneshard adapter consumes that manifest and emits `Other_24`-style GML without pushing MSL/GML concerns into solver or render core.

The standalone art boundary above the generic solver/render stack is:
- `toolsv2/art_generator.py`
- `toolsv2/ART_GENERATOR.md`

That layer is the intended reusable integration point for other skill-tree generators.

Export directly into a clean Stoneshard/MSL mod workspace:

```bash
python -m toolsv2.run_msl_mod_export ricochet --mod-source-dir D:\path\to\RicochetModGenerated
```

Or scaffold a clean editable workspace from an existing noisy `ModSources` folder and then export into it in one step:

```bash
python -m toolsv2.run_msl_mod_export ricochet --template-mod-source-dir D:\Games\Stoneshard_MODBRANCH\msl\ModSources\RicochetMod --mod-source-dir D:\code\stoneshard\mod_workspaces\RicochetModClean
```

That writes:
- generated branch/background sprite into `Sprites/`
- generated glow line sprites into `Sprites/`
- generated `Other_24.gml` into `Codes/`
- provenance files into `Generated/toolsv2/<project>/`

The scaffold step keeps only the editable mod project footprint:
- root project files such as `.cs`, `.csproj`, `icon.png`
- `Codes/`
- `Sprites/`
- generated provenance under `Generated/`

It intentionally drops unrelated scratch/docs/tooling folders from the copied workspace.

## CI

GitHub Actions runs the same unittest suite on every push and pull request.
