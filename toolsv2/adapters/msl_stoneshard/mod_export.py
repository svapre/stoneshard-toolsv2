"""Reusable Stoneshard/MSL mod-source exporter above generic branch/glow output.

This module deliberately stays in the adapter layer. It knows about:

- MSL mod-source folder conventions (`Sprites/`, `Codes/`, `Generated/`)
- `ctr_SkillPoint` constructor syntax
- `Other_24` packaging for one skill category

It does not change solver, routing, or generic glow contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from toolsv2.adapters.msl_stoneshard.glow_exporter import (
    build_stoneshard_other_24_gml,
)
from toolsv2.art_generator import generate_v1_art_bundle
from toolsv2.glow.contracts import GlowExportManifest, GlowLineAssetSpec
from toolsv2.glow.rasterizer import write_rasterized_glow_line
from toolsv2.glow.serialization import write_glow_export_manifest_json
from toolsv2.render_export import save_base_render_result
from toolsv2.run_branch import SkillTreeRunResult
from toolsv2.skill_tree_requirements import (
    load_skill_tree_requirement_spec,
    SkillTreeRequirementSpec,
)


def _sanitize_identifier(raw_value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", raw_value)
    if not sanitized:
        sanitized = "value"
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


def _line_asset_suffix(line_id: str) -> str:
    match = re.fullmatch(r"([A-Za-z_]+?)(\d+)", line_id)
    if match is None:
        return _sanitize_identifier(line_id)
    return f"{match.group(1)}_{match.group(2)}"


def _copy_file_preserving_relpath(
    source_root: Path,
    source_path: Path,
    target_root: Path,
) -> Path:
    relative_path = source_path.relative_to(source_root)
    target_path = target_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path


def _normalize_generated_asset_csproj(csproj_path: Path) -> None:
    tree = ET.parse(csproj_path)
    root = tree.getroot()
    namespace_prefix = ""
    if root.tag.startswith("{"):
        namespace_prefix = root.tag.split("}", 1)[0] + "}"

    removable_property_names = {
        "GlowGeneratorPython",
        "RicochetGlowContract",
        "RicochetGlowOutput",
        "RicochetBranchBase",
        "RicochetBranchOutput",
    }

    for property_group in root.findall(f"{namespace_prefix}PropertyGroup"):
        for child in list(property_group):
            tag_name = child.tag.removeprefix(namespace_prefix)
            if tag_name in removable_property_names:
                property_group.remove(child)

    for target in list(root.findall(f"{namespace_prefix}Target")):
        should_remove = False
        target_name = target.attrib.get("Name", "")
        if target_name.startswith("Generate"):
            should_remove = True
        for exec_node in target.findall(f".//{namespace_prefix}Exec"):
            command = exec_node.attrib.get("Command", "")
            if (
                "branch_glow_topology.py" in command
                or "primitive_topology_renderer.py" in command
                or "\\Tools\\" in command
                or "/Tools/" in command
            ):
                should_remove = True
        if should_remove:
            root.remove(target)

    tree.write(csproj_path, encoding="utf-8", xml_declaration=False)


def scaffold_clean_stoneshard_mod_workspace(
    source_mod_dir: str | Path,
    target_mod_dir: str | Path,
) -> StoneshardWorkspaceScaffoldResult:
    """Create a minimal editable mod workspace from a noisier source mod folder."""

    source_root = Path(source_mod_dir).resolve()
    target_root = Path(target_mod_dir).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    copied_paths: list[Path] = []

    for pattern in ("*.cs", "*.csproj", "icon.png"):
        for source_path in sorted(source_root.glob(pattern)):
            copied_paths.append(
                _copy_file_preserving_relpath(source_root, source_path, target_root)
            )

    codes_root = source_root / "Codes"
    if codes_root.exists():
        for source_path in sorted(codes_root.rglob("*.gml")):
            copied_paths.append(
                _copy_file_preserving_relpath(source_root, source_path, target_root)
            )

    sprites_root = source_root / "Sprites"
    if sprites_root.exists():
        for source_path in sorted(sprites_root.rglob("*.png")):
            filename = source_path.name.lower()
            if "_line_" in filename and filename.startswith("spr_"):
                continue
            copied_paths.append(
                _copy_file_preserving_relpath(source_root, source_path, target_root)
            )

    for copied_path in copied_paths:
        if copied_path.suffix.lower() == ".csproj":
            _normalize_generated_asset_csproj(copied_path)

    return StoneshardWorkspaceScaffoldResult(
        workspace_dir=target_root,
        copied_paths=tuple(copied_paths),
    )


@dataclass(frozen=True, slots=True)
class StoneshardPointBinding:
    """One mod-side binding from generic point id to a game skill object."""

    point_id: str
    variable_name: str
    skill_object_name: str

    def __post_init__(self) -> None:
        if not self.point_id:
            raise ValueError("StoneshardPointBinding.point_id must not be empty")
        if not self.variable_name:
            raise ValueError("StoneshardPointBinding.variable_name must not be empty")
        if not self.skill_object_name:
            raise ValueError("StoneshardPointBinding.skill_object_name must not be empty")


@dataclass(frozen=True, slots=True)
class StoneshardModWorkspaceConfig:
    """Content-side config for exporting one solved tree into one mod workspace."""

    config_id: str
    tree_json_path: Path
    branch_asset_name: str
    other_24_relpath: Path
    create_0_relpath: Path | None
    sprites_relpath: Path
    generated_relpath: Path
    point_bindings: tuple[StoneshardPointBinding, ...]
    connections_render_var: str = "connectionsRender"
    empty_sprite_asset_name: str = "s_empty"

    def __post_init__(self) -> None:
        if not self.config_id:
            raise ValueError("StoneshardModWorkspaceConfig.config_id must not be empty")
        if not self.branch_asset_name:
            raise ValueError("StoneshardModWorkspaceConfig.branch_asset_name must not be empty")
        if not self.point_bindings:
            raise ValueError("StoneshardModWorkspaceConfig.point_bindings must not be empty")
        if len({binding.point_id for binding in self.point_bindings}) != len(self.point_bindings):
            raise ValueError("StoneshardModWorkspaceConfig.point_bindings point ids must be unique")
        if len({binding.variable_name for binding in self.point_bindings}) != len(self.point_bindings):
            raise ValueError("StoneshardModWorkspaceConfig.point_bindings variable names must be unique")


@dataclass(frozen=True, slots=True)
class StoneshardModWorkspaceExportResult:
    """One exported mod workspace bundle."""

    mod_source_dir: Path
    branch_sprite_path: Path
    other_24_path: Path
    generated_other_24_path: Path
    manifest_path: Path
    line_png_paths: tuple[Path, ...]
    create_0_branch_asset_verified: bool
    run_result: SkillTreeRunResult
    manifest: GlowExportManifest


@dataclass(frozen=True, slots=True)
class StoneshardWorkspaceScaffoldResult:
    """One clean mod workspace scaffolded from an existing noisy source tree."""

    workspace_dir: Path
    copied_paths: tuple[Path, ...]


def _resolve_config_path(project_or_path: str | Path) -> Path:
    candidate = Path(project_or_path)
    if candidate.exists():
        return candidate.resolve()
    return (
        Path(__file__).resolve().parent
        / "mod_configs"
        / f"{project_or_path}.json"
    ).resolve()


def load_stoneshard_mod_workspace_config(
    project_or_path: str | Path,
) -> StoneshardModWorkspaceConfig:
    """Load one Stoneshard mod workspace config from JSON."""

    config_path = _resolve_config_path(project_or_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Stoneshard mod workspace config not found: {config_path}")
    raw_data = json.loads(config_path.read_text(encoding="utf-8"))

    def _required_string(key: str) -> str:
        value = raw_data.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Config field {key!r} must be a non-empty string")
        return value

    point_bindings_raw = raw_data.get("point_bindings")
    if not isinstance(point_bindings_raw, list) or not point_bindings_raw:
        raise ValueError("Config field 'point_bindings' must be a non-empty list")

    return StoneshardModWorkspaceConfig(
        config_id=_required_string("config_id"),
        tree_json_path=(config_path.parent / _required_string("tree_json_path")).resolve(),
        branch_asset_name=_required_string("branch_asset_name"),
        other_24_relpath=Path(_required_string("other_24_relpath")),
        create_0_relpath=(
            Path(raw_data["create_0_relpath"])
            if isinstance(raw_data.get("create_0_relpath"), str) and raw_data["create_0_relpath"]
            else None
        ),
        sprites_relpath=Path(_required_string("sprites_relpath")),
        generated_relpath=Path(_required_string("generated_relpath")),
        point_bindings=tuple(
            StoneshardPointBinding(
                point_id=binding["point_id"],
                variable_name=binding["variable_name"],
                skill_object_name=binding["skill_object_name"],
            )
            for binding in point_bindings_raw
        ),
        connections_render_var=raw_data.get("connections_render_var", "connectionsRender"),
        empty_sprite_asset_name=raw_data.get("empty_sprite_asset_name", "s_empty"),
    )


def _point_variable_names_by_point_id(
    config: StoneshardModWorkspaceConfig,
) -> dict[str, str]:
    return {
        binding.point_id: binding.variable_name
        for binding in config.point_bindings
    }


def _line_variable_names_by_line_id(
    manifest: GlowExportManifest,
) -> dict[str, str]:
    line_variable_names: dict[str, str] = {}
    for line_spec in manifest.line_specs:
        line_id = line_spec.line_id
        if line_id.startswith("line"):
            line_variable_names[line_id] = f"_{line_id}"
        else:
            line_variable_names[line_id] = f"_line_{_sanitize_identifier(line_id)}"
    return line_variable_names


def _build_full_other_24_gml(
    manifest: GlowExportManifest,
    config: StoneshardModWorkspaceConfig,
) -> str:
    point_specs_by_id = {
        point_spec.point_id: point_spec
        for point_spec in manifest.point_specs
    }
    configured_point_ids = {
        binding.point_id
        for binding in config.point_bindings
    }
    missing_point_ids = sorted(set(point_specs_by_id).difference(configured_point_ids))
    extra_point_ids = sorted(configured_point_ids.difference(point_specs_by_id))
    if missing_point_ids:
        raise ValueError(
            f"Mod config {config.config_id!r} is missing point bindings for: {missing_point_ids}"
        )
    if extra_point_ids:
        raise ValueError(
            f"Mod config {config.config_id!r} contains unknown point bindings: {extra_point_ids}"
        )

    lines: list[str] = [
        "event_inherited();",
        "",
    ]
    for binding in config.point_bindings:
        point_spec = point_specs_by_id[binding.point_id]
        lines.append(
            "var "
            f"{binding.variable_name} = new ctr_SkillPoint("
            f"{config.connections_render_var}, "
            f"{binding.skill_object_name}, "
            f"{point_spec.anchor_x}, "
            f"{point_spec.anchor_y}"
            ");"
        )
    lines.append("")

    body_export = build_stoneshard_other_24_gml(
        manifest,
        point_variable_names_by_point_id=_point_variable_names_by_point_id(config),
        line_variable_names_by_line_id=_line_variable_names_by_line_id(manifest),
        connections_render_var=config.connections_render_var,
        empty_sprite_asset_name=config.empty_sprite_asset_name,
        emit_event_inherited=False,
    )
    body_text = body_export.gml_text.strip()
    if body_text:
        lines.append(body_text)

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _branch_asset_verified(
    config: StoneshardModWorkspaceConfig,
    *,
    mod_source_dir: Path,
) -> bool:
    if config.create_0_relpath is None:
        return False
    create_path = mod_source_dir / config.create_0_relpath
    if not create_path.exists():
        return False
    create_text = create_path.read_text(encoding="utf-8")
    return config.branch_asset_name in create_text


def export_to_stoneshard_mod_workspace(
    config: StoneshardModWorkspaceConfig,
    mod_source_dir: str | Path,
    *,
    max_placement_seeds: int = 64,
    max_grid_attempts: int = 32,
) -> StoneshardModWorkspaceExportResult:
    """Export one requirement tree directly into one clean Stoneshard mod workspace."""

    mod_source_path = Path(mod_source_dir).resolve()
    sprites_dir = mod_source_path / config.sprites_relpath
    sprites_dir.mkdir(parents=True, exist_ok=True)
    generated_dir = mod_source_path / config.generated_relpath / config.config_id
    generated_dir.mkdir(parents=True, exist_ok=True)

    requirement_spec: SkillTreeRequirementSpec = load_skill_tree_requirement_spec(config.tree_json_path)
    branch_sprite_path = sprites_dir / f"{config.branch_asset_name}_0.png"
    art_bundle = generate_v1_art_bundle(
        requirement_spec,
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
    )
    save_base_render_result(art_bundle.base_render_result, branch_sprite_path)

    line_asset_specs: list[GlowLineAssetSpec] = []
    line_specs = []
    line_png_paths: list[Path] = []
    for rasterized in art_bundle.glow_build_result.rasterized_lines:
        asset_name = f"spr_{requirement_spec.tree_id.replace('-', '_')}_{_line_asset_suffix(rasterized.line_spec.line_id)}"
        rasterized = replace(
            rasterized,
            asset_spec=replace(
                rasterized.asset_spec,
                asset_name=asset_name,
            ),
        )
        sprite_path = sprites_dir / f"{asset_name}_0.png"
        line_png_paths.append(write_rasterized_glow_line(rasterized, sprite_path))
        line_asset_specs.append(
            GlowLineAssetSpec(
                asset_id=rasterized.asset_spec.asset_id,
                asset_name=rasterized.asset_spec.asset_name,
                origin_x=rasterized.asset_spec.origin_x,
                origin_y=rasterized.asset_spec.origin_y,
                png_path=str(sprite_path),
            )
        )
        line_specs.append(rasterized.line_spec)

    manifest = GlowExportManifest(
        tree_id=requirement_spec.tree_id,
        point_specs=art_bundle.glow_build_result.sections.point_specs,
        line_asset_specs=tuple(line_asset_specs),
        line_specs=tuple(line_specs),
        background_png_path=str(branch_sprite_path),
    )
    manifest_path = write_glow_export_manifest_json(
        manifest,
        generated_dir / "glow_manifest.json",
    )
    full_other_24_text = _build_full_other_24_gml(manifest, config)
    generated_other_24_path = generated_dir / "Other_24.generated.gml"
    generated_other_24_path.write_text(full_other_24_text, encoding="utf-8")
    other_24_path = mod_source_path / config.other_24_relpath
    other_24_path.parent.mkdir(parents=True, exist_ok=True)
    other_24_path.write_text(full_other_24_text, encoding="utf-8")

    return StoneshardModWorkspaceExportResult(
        mod_source_dir=mod_source_path,
        branch_sprite_path=branch_sprite_path,
        other_24_path=other_24_path,
        generated_other_24_path=generated_other_24_path,
        manifest_path=manifest_path,
        line_png_paths=tuple(line_png_paths),
        create_0_branch_asset_verified=_branch_asset_verified(
            config,
            mod_source_dir=mod_source_path,
        ),
        run_result=SkillTreeRunResult(
            requirement_spec=art_bundle.requirement_spec,
            compiled_content=art_bundle.compiled_content,
            solve_result=art_bundle.solve_result,
            output_path=branch_sprite_path,
        ),
        manifest=manifest,
    )
