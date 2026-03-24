"""Current file runner for requirement-spec JSON -> solve -> base render."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

from toolsv2.full_solve_orchestrator import (
    FullSolveResult,
    build_v1_estimated_full_solve_orchestrator,
)
from toolsv2.grid_expansion_policy import build_v1_explicit_band_expansion_policy
from toolsv2.layout_estimation import (
    LayoutDemandEstimate,
    V1RuleBasedLayoutDemandEstimator,
    build_same_band_multi_sink_split_pattern_rule,
)
from toolsv2.layout_profiles import (
    V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
    V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
    LayoutProfile,
    build_band_expansion_step_for_layout_pattern,
    build_v1_vanilla_skill_tree_layout_profile,
)
from toolsv2.render_export import render_v1_successful_solve_result, save_base_render_result
from toolsv2.render_layout_profiles import (
    RenderLayoutProfile,
    build_v1_vanilla_render_layout_profile,
)
from toolsv2.skill_tree_requirements import (
    CompiledSkillTreeContent,
    SkillTreeRequirementSpec,
    authored_tier_rail_ids_for_tree,
    compile_v1_skill_tree_to_graph_content,
    load_skill_tree_requirement_spec,
)
from toolsv2.solver_common import LogicalYRailId


@dataclass(frozen=True, slots=True)
class SkillTreeRunResult:
    """One end-to-end current runner result."""

    requirement_spec: SkillTreeRequirementSpec
    compiled_content: CompiledSkillTreeContent
    solve_result: FullSolveResult
    output_path: Path


def _default_dynamic_rail_ids(
    upper_tier_rail_id: LogicalYRailId,
    lower_tier_rail_id: LogicalYRailId,
    *,
    count: int,
    existing_ids: tuple[LogicalYRailId, ...] = (),
) -> tuple[LogicalYRailId, ...]:
    rail_ids = list(existing_ids[:count])
    while len(rail_ids) < count:
        rail_ids.append(
            LogicalYRailId(
                f"dyn::{upper_tier_rail_id}::{lower_tier_rail_id}::{len(rail_ids)}"
            )
        )
    return tuple(rail_ids)


def _build_default_grid_expansion_policy_builder(
    layout_profile: LayoutProfile,
):
    def _builder(estimate: LayoutDemandEstimate):
        steps = []
        for band in estimate.initial_grid.y_bands:
            if len(band.dynamic_rail_ids) == 0:
                steps.append(
                    build_band_expansion_step_for_layout_pattern(
                        layout_profile,
                        band_id=band.band_id,
                        pattern_id=V1_VANILLA_SINGLE_MID_BAND_LAYOUT_ID,
                        ordered_dynamic_rail_ids=_default_dynamic_rail_ids(
                            band.upper_authored_rail_id,
                            band.lower_authored_rail_id,
                            count=1,
                        ),
                    )
                )

        try:
            for band in estimate.initial_grid.y_bands:
                if len(band.dynamic_rail_ids) >= 2:
                    continue
                steps.append(
                    build_band_expansion_step_for_layout_pattern(
                        layout_profile,
                        band_id=band.band_id,
                        pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
                        ordered_dynamic_rail_ids=_default_dynamic_rail_ids(
                            band.upper_authored_rail_id,
                            band.lower_authored_rail_id,
                            count=2,
                            existing_ids=band.dynamic_rail_ids,
                        ),
                    )
                )
        except KeyError:
            pass

        return build_v1_explicit_band_expansion_policy(
            initial_grid=estimate.initial_grid,
            steps=tuple(steps),
        )

    return _builder


def _render_layout_profile_for_tree(
    requirement_spec: SkillTreeRequirementSpec,
    *,
    base_profile: RenderLayoutProfile | None = None,
) -> RenderLayoutProfile:
    render_layout_profile = (
        build_v1_vanilla_render_layout_profile()
        if base_profile is None
        else base_profile
    )
    compiled = compile_v1_skill_tree_to_graph_content(requirement_spec)
    if compiled.background_asset_ref is not None:
        render_layout_profile = replace(
            render_layout_profile,
            default_background_asset_ref=compiled.background_asset_ref,
        )
    return render_layout_profile


def _default_output_path(requirement_spec: SkillTreeRequirementSpec) -> Path:
    return Path(__file__).resolve().parent / "output" / f"{requirement_spec.tree_id}.png"


def run_v1_requirement_tree(
    requirement_spec: SkillTreeRequirementSpec,
    *,
    out_path: str | Path | None = None,
    max_placement_seeds: int = 64,
    max_grid_attempts: int = 32,
    layout_profile: LayoutProfile | None = None,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> SkillTreeRunResult:
    """Run the current requirement-spec tree through solve and base render."""

    if layout_profile is None:
        layout_profile = build_v1_vanilla_skill_tree_layout_profile()
    compiled_content = compile_v1_skill_tree_to_graph_content(requirement_spec)
    estimator = V1RuleBasedLayoutDemandEstimator(
        layout_profile=layout_profile,
        authored_tier_rail_ids=authored_tier_rail_ids_for_tree(requirement_spec),
        band_layout_demand_rules=(
            build_same_band_multi_sink_split_pattern_rule(
                split_pattern_id=V1_VANILLA_FOUR_TIER_SPLIT_PAIR_BAND_LAYOUT_ID,
            ),
        ),
    )
    orchestrator = build_v1_estimated_full_solve_orchestrator(
        layout_demand_estimator=estimator,
        grid_expansion_policy_builder=_build_default_grid_expansion_policy_builder(
            layout_profile
        ),
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
        minimum_same_row_gap=layout_profile.minimum_same_row_gap,
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
    render_result = render_v1_successful_solve_result(
        solve_result.successful_current_grid_result,
        render_layout_profile=actual_render_layout_profile,
    )
    output_path = save_base_render_result(
        render_result,
        _default_output_path(requirement_spec) if out_path is None else out_path,
    )
    return SkillTreeRunResult(
        requirement_spec=requirement_spec,
        compiled_content=compiled_content,
        solve_result=solve_result,
        output_path=output_path,
    )


def run_v1_requirement_tree_json(
    tree_path: str | Path,
    *,
    out_path: str | Path | None = None,
    max_placement_seeds: int = 64,
    max_grid_attempts: int = 32,
) -> SkillTreeRunResult:
    """Load one requirement JSON file, solve it, and save the base PNG."""

    requirement_spec = load_skill_tree_requirement_spec(tree_path)
    return run_v1_requirement_tree(
        requirement_spec,
        out_path=out_path,
        max_placement_seeds=max_placement_seeds,
        max_grid_attempts=max_grid_attempts,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a base branch image from the current requirement JSON."
    )
    parser.add_argument(
        "tree",
        type=Path,
        help="Path to the requirement-spec JSON file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output PNG path. Defaults to toolsv2/output/<tree_id>.png",
    )
    parser.add_argument(
        "--max-placement-seeds",
        type=int,
        default=64,
        help="Maximum placement seeds to try per grid. Default: 64",
    )
    parser.add_argument(
        "--max-grid-attempts",
        type=int,
        default=32,
        help="Maximum grid attempts across expansions. Default: 32",
    )
    args = parser.parse_args()

    result = run_v1_requirement_tree_json(
        args.tree,
        out_path=args.out,
        max_placement_seeds=args.max_placement_seeds,
        max_grid_attempts=args.max_grid_attempts,
    )
    print(result.output_path)


if __name__ == "__main__":
    main()
