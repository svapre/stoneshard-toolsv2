"""JSON-friendly serialization helpers for the generic glow export manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from toolsv2.glow.contracts import GlowExportManifest


def glow_export_manifest_to_dict(
    manifest: GlowExportManifest,
) -> dict[str, Any]:
    """Convert one glow export manifest into a JSON-friendly dictionary."""

    return {
        "tree_id": manifest.tree_id,
        "background_png_path": manifest.background_png_path,
        "point_specs": [
            {
                "point_id": point.point_id,
                "anchor_x": point.anchor_x,
                "anchor_y": point.anchor_y,
                "display_name": point.display_name,
                "point_dependency_groups": [
                    list(group) for group in point.point_dependency_groups
                ],
                "line_dependency_groups": [
                    list(group) for group in point.line_dependency_groups
                ],
            }
            for point in manifest.point_specs
        ],
        "line_asset_specs": [
            {
                "asset_id": asset.asset_id,
                "asset_name": asset.asset_name,
                "origin_x": asset.origin_x,
                "origin_y": asset.origin_y,
                "png_path": asset.png_path,
            }
            for asset in manifest.line_asset_specs
        ],
        "line_specs": [
            {
                "line_id": line.line_id,
                "asset_id": line.asset_id,
                "anchor_x": line.anchor_x,
                "anchor_y": line.anchor_y,
                "draw_knot": line.draw_knot,
                "point_dependency_groups": [
                    list(group) for group in line.point_dependency_groups
                ],
                "line_dependency_groups": [
                    list(group) for group in line.line_dependency_groups
                ],
            }
            for line in manifest.line_specs
        ],
    }


def glow_export_manifest_to_json(
    manifest: GlowExportManifest,
    *,
    indent: int = 2,
) -> str:
    """Serialize one glow export manifest into deterministic JSON text."""

    return json.dumps(glow_export_manifest_to_dict(manifest), indent=indent, sort_keys=True)


def write_glow_export_manifest_json(
    manifest: GlowExportManifest,
    out_path: str | Path,
    *,
    indent: int = 2,
) -> Path:
    """Write one glow export manifest to disk as JSON."""

    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        glow_export_manifest_to_json(manifest, indent=indent) + "\n",
        encoding="utf-8",
    )
    return output_path
