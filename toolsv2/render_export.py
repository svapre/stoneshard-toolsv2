"""Thin export/testing helpers for the current base renderer."""

from __future__ import annotations

from pathlib import Path

from toolsv2.base_renderer import BaseRenderResult, build_v1_base_renderer
from toolsv2.render_layout_profiles import (
    RenderLayoutProfile,
    build_v1_vanilla_render_layout_profile,
)
from toolsv2.render_mapper import build_static_rail_pixel_mapper
from toolsv2.solve_pipeline import CurrentGridSolveResult
from toolsv2.solver_common import ActiveGridState
from toolsv2.solver_runtime import PortGraphState
from toolsv2.visual_profiles import VisualProfileCatalog


def render_v1_base_state(
    *,
    active_grid: ActiveGridState,
    state: PortGraphState,
    visual_profile_catalog: VisualProfileCatalog,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> BaseRenderResult:
    """Render one committed runtime snapshot into the current base image."""

    if render_layout_profile is None:
        render_layout_profile = build_v1_vanilla_render_layout_profile()
    mapper = build_static_rail_pixel_mapper(
        active_grid=active_grid,
        render_layout_profile=render_layout_profile,
    )
    renderer = build_v1_base_renderer()
    return renderer(
        state,
        mapper,
        visual_profile_catalog,
        render_layout_profile=render_layout_profile,
    )


def render_v1_successful_solve_result(
    solve_result: CurrentGridSolveResult,
    *,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> BaseRenderResult:
    """Render the base image from one successful current-grid solve result."""

    if solve_result.status != "success" or solve_result.final_state is None:
        raise ValueError("render_v1_successful_solve_result requires a successful solve result")
    return render_v1_base_state(
        active_grid=solve_result.active_grid,
        state=solve_result.final_state,
        visual_profile_catalog=solve_result.loaded_content.visual_profile_catalog,
        render_layout_profile=render_layout_profile,
    )


def save_base_render_result(
    render_result: BaseRenderResult,
    out_path: str | Path,
) -> Path:
    """Save one rendered base image to disk as PNG."""

    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_result.image.save(output_path)
    return output_path
