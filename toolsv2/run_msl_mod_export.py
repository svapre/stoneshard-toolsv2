"""Export one requirement tree directly into one clean Stoneshard/MSL mod workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from toolsv2.adapters.msl_stoneshard import (
    export_to_stoneshard_mod_workspace,
    load_stoneshard_mod_workspace_config,
    scaffold_clean_stoneshard_mod_workspace,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate branch/glow files directly into one clean Stoneshard mod workspace."
    )
    parser.add_argument(
        "project",
        help="Project config name (for example: ricochet) or a direct config JSON path",
    )
    parser.add_argument(
        "--mod-source-dir",
        type=Path,
        required=True,
        help="Path to the clean mod workspace folder to write into",
    )
    parser.add_argument(
        "--template-mod-source-dir",
        type=Path,
        default=None,
        help="Optional existing noisy mod-source folder to scaffold a clean workspace from before export",
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

    config = load_stoneshard_mod_workspace_config(args.project)
    if args.template_mod_source_dir is not None:
        scaffold_clean_stoneshard_mod_workspace(
            args.template_mod_source_dir,
            args.mod_source_dir,
        )
    result = export_to_stoneshard_mod_workspace(
        config,
        args.mod_source_dir,
        max_placement_seeds=args.max_placement_seeds,
        max_grid_attempts=args.max_grid_attempts,
    )
    print(result.mod_source_dir)


if __name__ == "__main__":
    main()
