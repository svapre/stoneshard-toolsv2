"""Standalone art generation API for solved skill-tree requirements.

This module is intentionally generic:
- it reads requirement specs
- solves them
- builds branch/background art
- builds glow line art and the generic glow manifest
- exposes intermediate render/glow artifacts in memory

It does not emit Stoneshard/MSL-specific code. Adapter layers can consume the
returned bundle or the written generic output folder.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from toolsv2.base_renderer import BaseRenderResult
from toolsv2.glow.contracts import GlowExportManifest, GlowLineAssetSpec
from toolsv2.glow.rasterizer import (
    GlowRasterizedLine,
    rasterize_glow_section,
    write_rasterized_glow_line,
)
from toolsv2.glow.section_builder import (
    GlowSectionBuildResult,
    build_glow_port_pixel_lookup_for_successful_run,
    build_glow_sections_for_successful_run,
)
from toolsv2.glow.serialization import write_glow_export_manifest_json
from toolsv2.layout_estimation import (
    V1RuleBasedLayoutDemandEstimator,
    build_adjacent_authored_flow_band_rule,
    build_same_band_multi_sink_split_pattern_rule,
    build_single_sink_mediated_band_rule,
)
from toolsv2.layout_profiles import (
    LayoutProfile,
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    build_v1_vanilla_skill_tree_layout_profile,
)
from toolsv2.render_export import render_v1_successful_solve_result, save_base_render_result
from toolsv2.render_layout_profiles import RenderLayoutProfile
from toolsv2.render_template_loader import build_cached_render_template_loader
from toolsv2.run_branch import (
    _build_default_grid_expansion_policy_builder,
    _render_layout_profile_for_tree,
    SkillTreeRunResult,
)
from toolsv2.skill_tree_requirements import (
    CompiledSkillTreeContent,
    SkillTreeRequirementSpec,
    authored_tier_rail_ids_for_tree,
    compile_v1_skill_tree_to_graph_content,
    load_skill_tree_requirement_spec,
)
from toolsv2.full_solve_orchestrator import FullSolveResult, build_v1_estimated_full_solve_orchestrator


GlowAssetNameBuilder = Callable[[SkillTreeRequirementSpec, int, str], str]


@dataclass(frozen=True, slots=True)
class StandaloneGlowBuildResult:
    """Generic in-memory glow artifacts before filesystem export."""

    sections: GlowSectionBuildResult
    port_pixels_by_port_ref: Mapping
    rasterized_lines: tuple[GlowRasterizedLine, ...]
    manifest: GlowExportManifest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "port_pixels_by_port_ref",
            MappingProxyType(dict(self.port_pixels_by_port_ref)),
        )


@dataclass(frozen=True, slots=True)
class StandaloneArtGenerationResult:
    """One standalone branch+glow art generation bundle."""

    requirement_spec: SkillTreeRequirementSpec
    compiled_content: CompiledSkillTreeContent
    solve_result: FullSolveResult
    render_layout_profile: RenderLayoutProfile
    base_render_result: BaseRenderResult
    glow_build_result: StandaloneGlowBuildResult


@dataclass(frozen=True, slots=True)
class WrittenStandaloneArtBundle:
    """One written standalone art output folder."""

    output_dir: Path
    branch_png_path: Path
    layer_png_paths: tuple[Path, ...]
    glow_manifest_path: Path
    glow_line_png_paths: tuple[Path, ...]


def _default_glow_asset_name(
    requirement_spec: SkillTreeRequirementSpec,
    index: int,
    _section_id: str,
) -> str:
    tree_slug = requirement_spec.tree_id.replace("-", "_")
    return f"spr_{tree_slug}_line_{index}"


def _build_orchestrator(
    requirement_spec: SkillTreeRequirementSpec,
    *,
    layout_profile: LayoutProfile,
    max_placement_seeds: int,
    max_grid_attempts: int,
):
    estimator = V1RuleBasedLayoutDemandEstimator(
        layout_profile=layout_profile,
        authored_tier_rail_ids=authored_tier_rail_ids_for_tree(requirement_spec),
        band_layout_demand_rules=(
            build_adjacent_authored_flow_band_rule(
                pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
            ),
            build_single_sink_mediated_band_rule(
                pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
            ),
            build_same_band_multi_sink_split_pattern_rule(
                split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
            ),
        ),
    )
    return build_v1_estimated_full_solve_orchestrator(
        layout_demand_estimator=estimator,
        grid_expansion_policy_builder=_build_default_grid_expansion_policy_builder(
            layout_profile
        ),
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
        minimum_same_row_gap=layout_profile.minimum_same_row_gap,
    )


def generate_v1_art_bundle(
    requirement_spec: SkillTreeRequirementSpec,
    *,
    layout_profile: LayoutProfile | None = None,
    render_layout_profile: RenderLayoutProfile | None = None,
    max_placement_seeds: int = 64,
    max_grid_attempts: int = 32,
    glow_asset_name_builder: GlowAssetNameBuilder | None = None,
) -> StandaloneArtGenerationResult:
    """Build one standalone branch+glow art bundle in memory."""

    if layout_profile is None:
        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
    compiled_content = compile_v1_skill_tree_to_graph_content(requirement_spec)
    orchestrator = _build_orchestrator(
        requirement_spec,
        layout_profile=layout_profile,
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
    )
    solve_result = orchestrator(compiled_content.graph_content)
    if solve_result.status != "success" or solve_result.successful_current_grid_result is None:
        raise RuntimeError(
            f"Failed to solve requirement tree across tried grids: {requirement_spec.tree_id}"
        )

    actual_render_layout_profile = _render_layout_profile_for_tree(
        requirement_spec,
        base_profile=render_layout_profile,
    )
    base_render_result = render_v1_successful_solve_result(
        solve_result.successful_current_grid_result,
        render_layout_profile=actual_render_layout_profile,
    )

    run_like = SkillTreeRunResult(
        requirement_spec=requirement_spec,
        compiled_content=compiled_content,
        solve_result=solve_result,
        output_path=Path(),
    )
    section_result = build_glow_sections_for_successful_run(
        run_like,
        render_layout_profile=actual_render_layout_profile,
    )
    port_pixels_by_port_ref = build_glow_port_pixel_lookup_for_successful_run(
        run_like,
        render_layout_profile=actual_render_layout_profile,
    )
    visual_profile_catalog = solve_result.successful_current_grid_result.loaded_content.visual_profile_catalog
    template_loader = build_cached_render_template_loader()
    name_builder = _default_glow_asset_name if glow_asset_name_builder is None else glow_asset_name_builder

    rasterized_lines: list[GlowRasterizedLine] = []
    line_asset_specs: list[GlowLineAssetSpec] = []
    line_specs = []
    for index, section in enumerate(section_result.sections, start=1):
        asset_name = name_builder(requirement_spec, index, section.section_id)
        rasterized = rasterize_glow_section(
            section,
            asset_name=asset_name,
            port_pixels_by_port_ref=port_pixels_by_port_ref,
            visual_profile_catalog=visual_profile_catalog,
            template_loader=template_loader,
        )
        rasterized_lines.append(rasterized)
        line_asset_specs.append(
            GlowLineAssetSpec(
                asset_id=rasterized.asset_spec.asset_id,
                asset_name=rasterized.asset_spec.asset_name,
                origin_x=rasterized.asset_spec.origin_x,
                origin_y=rasterized.asset_spec.origin_y,
            )
        )
        line_specs.append(rasterized.line_spec)

    glow_manifest = GlowExportManifest(
        tree_id=requirement_spec.tree_id,
        point_specs=section_result.point_specs,
        line_asset_specs=tuple(line_asset_specs),
        line_specs=tuple(line_specs),
    )
    glow_build_result = StandaloneGlowBuildResult(
        sections=section_result,
        port_pixels_by_port_ref=port_pixels_by_port_ref,
        rasterized_lines=tuple(rasterized_lines),
        manifest=glow_manifest,
    )
    return StandaloneArtGenerationResult(
        requirement_spec=requirement_spec,
        compiled_content=compiled_content,
        solve_result=solve_result,
        render_layout_profile=actual_render_layout_profile,
        base_render_result=base_render_result,
        glow_build_result=glow_build_result,
    )


def generate_v1_art_bundle_json(
    tree_path: str | Path,
    *,
    layout_profile: LayoutProfile | None = None,
    render_layout_profile: RenderLayoutProfile | None = None,
    max_placement_seeds: int = 64,
    max_grid_attempts: int = 32,
    glow_asset_name_builder: GlowAssetNameBuilder | None = None,
) -> StandaloneArtGenerationResult:
    """Load one requirement JSON and build the standalone art bundle."""

    return generate_v1_art_bundle(
        load_skill_tree_requirement_spec(tree_path),
        layout_profile=layout_profile,
        render_layout_profile=render_layout_profile,
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
        glow_asset_name_builder=glow_asset_name_builder,
    )


def write_standalone_art_bundle(
    art_bundle: StandaloneArtGenerationResult,
    out_dir: str | Path,
    *,
    branch_filename: str | None = None,
    write_layer_images: bool = True,
) -> WrittenStandaloneArtBundle:
    """Write one standalone art bundle to a clean generic output folder."""

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    branch_path = output_dir / (
        branch_filename
        if branch_filename is not None
        else f"{art_bundle.requirement_spec.tree_id}.png"
    )
    save_base_render_result(art_bundle.base_render_result, branch_path)

    layer_png_paths: list[Path] = []
    if write_layer_images:
        layers_dir = output_dir / "layers"
        layers_dir.mkdir(parents=True, exist_ok=True)
        background_path = layers_dir / "background.png"
        art_bundle.base_render_result.background_image.save(background_path)
        layer_png_paths.append(background_path)
        for layer_image in art_bundle.base_render_result.layer_images:
            layer_path = layers_dir / f"{layer_image.layer_id}.png"
            layer_image.image.save(layer_path)
            layer_png_paths.append(layer_path)

    glow_dir = output_dir / "glow"
    lines_dir = glow_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    written_line_png_paths: list[Path] = []
    written_asset_specs: list[GlowLineAssetSpec] = []
    for rasterized_line in art_bundle.glow_build_result.rasterized_lines:
        png_path = lines_dir / f"{rasterized_line.asset_spec.asset_name}_0.png"
        written_line_png_paths.append(write_rasterized_glow_line(rasterized_line, png_path))
        written_asset_specs.append(
            replace(
                rasterized_line.asset_spec,
                png_path=str(png_path),
            )
        )
    written_manifest = replace(
        art_bundle.glow_build_result.manifest,
        line_asset_specs=tuple(written_asset_specs),
        background_png_path=str(branch_path),
    )
    glow_manifest_path = write_glow_export_manifest_json(
        written_manifest,
        glow_dir / "glow_manifest.json",
    )
    return WrittenStandaloneArtBundle(
        output_dir=output_dir,
        branch_png_path=branch_path,
        layer_png_paths=tuple(layer_png_paths),
        glow_manifest_path=glow_manifest_path,
        glow_line_png_paths=tuple(written_line_png_paths),
    )
