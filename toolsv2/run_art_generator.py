"""Generic standalone art-generator CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from toolsv2.art_generator import generate_v1_art_bundle_json, write_standalone_art_bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate standalone branch/glow art plus intermediate layer PNGs from one requirement JSON."
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
        help="Optional output directory. Defaults to toolsv2/output/<tree_id>_art",
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

    art_bundle = generate_v1_art_bundle_json(
        args.tree,
        max_placement_seeds=args.max_placement_seeds,
        max_grid_attempts=args.max_grid_attempts,
    )
    output_dir = (
        args.out_dir
        if args.out_dir is not None
        else Path(__file__).resolve().parent / "output" / f"{art_bundle.requirement_spec.tree_id}_art"
    )
    written = write_standalone_art_bundle(
        art_bundle,
        output_dir,
    )
    print(written.output_dir)


if __name__ == "__main__":
    main()
