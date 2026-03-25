"""Stoneshard/MSL adapter for generic glow export manifests.

This module deliberately sits outside solver and generic render core. It knows
about `ctr_SkillLine`, `addConnectedPoints`, `addConnectedLines`, and the
`Other_24` wiring style expected by Stoneshard/MSL consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from toolsv2.glow.contracts import GlowDependencyGroups, GlowExportManifest


def _sanitize_gml_identifier(raw_value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", raw_value)
    if not sanitized:
        sanitized = "value"
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


def _unique_variable_names(
    raw_ids: tuple[str, ...],
    *,
    prefix: str,
) -> Mapping[str, str]:
    assigned: dict[str, str] = {}
    used_names: set[str] = set()
    for raw_id in raw_ids:
        base_name = _sanitize_gml_identifier(f"{prefix}{raw_id}")
        name = base_name
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{base_name}_{suffix}"
        assigned[raw_id] = name
        used_names.add(name)
    return MappingProxyType(assigned)


def build_default_point_variable_names(
    manifest: GlowExportManifest,
) -> Mapping[str, str]:
    """Return deterministic default GML variable names for manifest points."""

    return _unique_variable_names(
        tuple(point.point_id for point in manifest.point_specs),
        prefix="_",
    )


def build_default_stoneshard_line_variable_names(
    manifest: GlowExportManifest,
) -> Mapping[str, str]:
    """Return deterministic default GML variable names for manifest lines."""

    return _unique_variable_names(
        tuple(line.line_id for line in manifest.line_specs),
        prefix="_line_",
    )


def _emit_grouped_call(
    receiver_var: str,
    method_name: str,
    dependency_groups: GlowDependencyGroups,
    id_to_var_name: Mapping[str, str],
) -> str | None:
    if not dependency_groups:
        return None
    arguments = ", ".join(
        "[" + ", ".join(id_to_var_name[dependency_id] for dependency_id in group) + "]"
        for group in dependency_groups
    )
    return f"{receiver_var}.{method_name}({arguments});"


@dataclass(frozen=True, slots=True)
class StoneshardOther24Export:
    """One rendered `Other_24`-style GML block plus generated line variable names."""

    gml_text: str
    point_variable_names_by_point_id: Mapping[str, str]
    line_variable_names_by_line_id: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "point_variable_names_by_point_id",
            MappingProxyType(dict(self.point_variable_names_by_point_id)),
        )
        object.__setattr__(
            self,
            "line_variable_names_by_line_id",
            MappingProxyType(dict(self.line_variable_names_by_line_id)),
        )


def build_stoneshard_other_24_gml(
    manifest: GlowExportManifest,
    *,
    point_variable_names_by_point_id: Mapping[str, str] | None = None,
    line_variable_names_by_line_id: Mapping[str, str] | None = None,
    connections_render_var: str = "connectionsRender",
    empty_sprite_asset_name: str = "s_empty",
    emit_event_inherited: bool = True,
) -> StoneshardOther24Export:
    """Render one generic glow manifest into Stoneshard `Other_24`-style GML."""

    if point_variable_names_by_point_id is None:
        point_variable_names_by_point_id = build_default_point_variable_names(manifest)
    else:
        point_variable_names_by_point_id = MappingProxyType(dict(point_variable_names_by_point_id))
    if line_variable_names_by_line_id is None:
        line_variable_names_by_line_id = build_default_stoneshard_line_variable_names(manifest)
    else:
        line_variable_names_by_line_id = MappingProxyType(dict(line_variable_names_by_line_id))

    missing_point_ids = {
        point.point_id
        for point in manifest.point_specs
        if point.point_id not in point_variable_names_by_point_id
    }
    if missing_point_ids:
        missing = ", ".join(sorted(missing_point_ids))
        raise ValueError(f"Missing point variable names for manifest points: {missing}")

    missing_line_ids = {
        line.line_id
        for line in manifest.line_specs
        if line.line_id not in line_variable_names_by_line_id
    }
    if missing_line_ids:
        missing = ", ".join(sorted(missing_line_ids))
        raise ValueError(f"Missing line variable names for manifest lines: {missing}")

    asset_specs_by_id = {
        asset.asset_id: asset
        for asset in manifest.line_asset_specs
    }
    lines: list[str] = []
    if emit_event_inherited:
        lines.extend(
            [
                "event_inherited();",
                "",
            ]
        )

    for line_spec in manifest.line_specs:
        line_var_name = line_variable_names_by_line_id[line_spec.line_id]
        sprite_var_name = f"{line_var_name}_spr"
        asset_spec = asset_specs_by_id[line_spec.asset_id]
        lines.append(
            f'var {sprite_var_name} = asset_get_index("{asset_spec.asset_name}");'
        )
        lines.append(
            f'if ({sprite_var_name} == -1) {sprite_var_name} = asset_get_index("{empty_sprite_asset_name}");'
        )
        lines.append(
            f"sprite_set_offset({sprite_var_name}, {asset_spec.origin_x}, {asset_spec.origin_y});"
        )
        constructor_args = [
            connections_render_var,
            sprite_var_name,
            str(line_spec.anchor_x),
            str(line_spec.anchor_y),
        ]
        if line_spec.draw_knot:
            constructor_args.append("true")
        lines.append(
            f"var {line_var_name} = new ctr_SkillLine({', '.join(constructor_args)});"
        )

    if manifest.line_specs:
        lines.append("")

    for point_spec in manifest.point_specs:
        point_var_name = point_variable_names_by_point_id[point_spec.point_id]
        point_call = _emit_grouped_call(
            point_var_name,
            "addConnectedPoints",
            point_spec.point_dependency_groups,
            point_variable_names_by_point_id,
        )
        if point_call is not None:
            lines.append(point_call)
        line_call = _emit_grouped_call(
            point_var_name,
            "addConnectedLines",
            point_spec.line_dependency_groups,
            line_variable_names_by_line_id,
        )
        if line_call is not None:
            lines.append(line_call)

    if manifest.point_specs:
        lines.append("")

    for line_spec in manifest.line_specs:
        line_var_name = line_variable_names_by_line_id[line_spec.line_id]
        point_call = _emit_grouped_call(
            line_var_name,
            "addConnectedPoints",
            line_spec.point_dependency_groups,
            point_variable_names_by_point_id,
        )
        if point_call is not None:
            lines.append(point_call)
        line_call = _emit_grouped_call(
            line_var_name,
            "addConnectedLines",
            line_spec.line_dependency_groups,
            line_variable_names_by_line_id,
        )
        if line_call is not None:
            lines.append(line_call)

    while lines and lines[-1] == "":
        lines.pop()

    return StoneshardOther24Export(
        gml_text="\n".join(lines) + "\n",
        point_variable_names_by_point_id=point_variable_names_by_point_id,
        line_variable_names_by_line_id=line_variable_names_by_line_id,
    )


def write_stoneshard_other_24_gml(
    manifest: GlowExportManifest,
    out_path: str | Path,
    *,
    point_variable_names_by_point_id: Mapping[str, str] | None = None,
    line_variable_names_by_line_id: Mapping[str, str] | None = None,
    connections_render_var: str = "connectionsRender",
    empty_sprite_asset_name: str = "s_empty",
    emit_event_inherited: bool = True,
) -> Path:
    """Write one Stoneshard `Other_24`-style glow GML block to disk."""

    export = build_stoneshard_other_24_gml(
        manifest,
        point_variable_names_by_point_id=point_variable_names_by_point_id,
        line_variable_names_by_line_id=line_variable_names_by_line_id,
        connections_render_var=connections_render_var,
        empty_sprite_asset_name=empty_sprite_asset_name,
        emit_event_inherited=emit_event_inherited,
    )
    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export.gml_text, encoding="utf-8")
    return output_path
