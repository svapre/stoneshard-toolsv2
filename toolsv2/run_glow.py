"""Current file runner for requirement JSON -> solve -> background + glow export."""

from __future__ import annotations

import argparse
from pathlib import Path

from toolsv2.glow.export import export_glow_for_successful_run
from toolsv2.run_branch import run_v1_requirement_tree_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate background and glow export files from one requirement JSON."
    )
    parser.add_argument(
        "tree",
        type=Path,
        help="Path to the requirement-spec JSON file",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional glow output directory. Defaults to toolsv2/output/<tree_id>_glow",
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

    run_result = run_v1_requirement_tree_json(
        args.tree,
        max_placement_seeds=args.max_placement_seeds,
        max_grid_attempts=args.max_grid_attempts,
    )
    glow_result = export_glow_for_successful_run(
        run_result,
        out_dir=args.out_dir,
    )
    print(glow_result.output_dir)


if __name__ == "__main__":
    main()
