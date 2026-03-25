"""End-to-end glow export helpers above successful solved requirement trees."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from toolsv2.adapters.msl_stoneshard.glow_exporter import write_stoneshard_other_24_gml
from toolsv2.glow.contracts import GlowExportManifest, GlowLineAssetSpec
from toolsv2.glow.rasterizer import rasterize_glow_section, write_rasterized_glow_line
from toolsv2.glow.section_builder import (
    build_glow_port_pixel_lookup_for_successful_run,
    build_glow_sections_for_successful_run,
)
from toolsv2.glow.serialization import write_glow_export_manifest_json
from toolsv2.render_layout_profiles import RenderLayoutProfile
from toolsv2.render_template_loader import build_cached_render_template_loader
from toolsv2.run_branch import SkillTreeRunResult


@dataclass(frozen=True, slots=True)
class GlowExportResult:
    """One saved glow export bundle."""

    output_dir: Path
    manifest: GlowExportManifest
    manifest_path: Path
    other_24_path: Path
    line_png_paths: tuple[Path, ...]


def _default_glow_output_dir(run_result: SkillTreeRunResult) -> Path:
    return run_result.output_path.with_name(f"{run_result.requirement_spec.tree_id}_glow")


def export_glow_for_successful_run(
    run_result: SkillTreeRunResult,
    *,
    out_dir: str | Path | None = None,
    render_layout_profile: RenderLayoutProfile | None = None,
    sprite_name_prefix: str | None = None,
) -> GlowExportResult:
    """Rasterize glow lines and emit a generic manifest plus Stoneshard GML."""

    output_dir = _default_glow_output_dir(run_result) if out_dir is None else Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    lines_dir = output_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    section_result = build_glow_sections_for_successful_run(
        run_result,
        render_layout_profile=render_layout_profile,
    )
    port_pixels_by_port_ref = build_glow_port_pixel_lookup_for_successful_run(
        run_result,
        render_layout_profile=render_layout_profile,
    )
    visual_profile_catalog = (
        run_result.solve_result.successful_current_grid_result.loaded_content.visual_profile_catalog
    )
    template_loader = build_cached_render_template_loader()

    tree_slug = run_result.requirement_spec.tree_id.replace("-", "_")
    name_prefix = (
        f"spr_{tree_slug}_line_"
        if sprite_name_prefix is None
        else sprite_name_prefix
    )

    asset_specs = []
    line_specs = []
    line_png_paths: list[Path] = []
    for index, section in enumerate(section_result.sections, start=1):
        asset_name = f"{name_prefix}{index}"
        rasterized = rasterize_glow_section(
            section,
            asset_name=asset_name,
            port_pixels_by_port_ref=port_pixels_by_port_ref,
            visual_profile_catalog=visual_profile_catalog,
            template_loader=template_loader,
        )
        png_path = lines_dir / f"{asset_name}_0.png"
        line_png_paths.append(write_rasterized_glow_line(rasterized, png_path))
        asset_specs.append(
            GlowLineAssetSpec(
                asset_id=rasterized.asset_spec.asset_id,
                asset_name=rasterized.asset_spec.asset_name,
                origin_x=rasterized.asset_spec.origin_x,
                origin_y=rasterized.asset_spec.origin_y,
                png_path=str(png_path),
            )
        )
        line_specs.append(rasterized.line_spec)

    manifest = GlowExportManifest(
        tree_id=run_result.requirement_spec.tree_id,
        point_specs=section_result.point_specs,
        line_asset_specs=tuple(asset_specs),
        line_specs=tuple(line_specs),
        background_png_path=str(run_result.output_path),
    )
    manifest_path = write_glow_export_manifest_json(
        manifest,
        output_dir / "glow_manifest.json",
    )
    other_24_path = write_stoneshard_other_24_gml(
        manifest,
        output_dir / "Other_24.gml",
    )
    return GlowExportResult(
        output_dir=output_dir,
        manifest=manifest,
        manifest_path=manifest_path,
        other_24_path=other_24_path,
        line_png_paths=tuple(line_png_paths),
    )
