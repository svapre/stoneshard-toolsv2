"""Generic glow export manifest contracts.

These types intentionally stop at the stable export boundary:

- point instances and their activation dependencies
- line sprite assets and line instances
- enough metadata for downstream adapters to emit engine-specific files

They do not embed Stoneshard/MSL-specific naming rules, GML syntax, or shader
assumptions. Those belong in adapter layers outside solver/render core.
"""

from __future__ import annotations

from dataclasses import dataclass


GlowDependencyGroups = tuple[tuple[str, ...], ...]


def _normalize_dependency_groups(
    field_name: str,
    dependency_groups: GlowDependencyGroups,
) -> GlowDependencyGroups:
    normalized_groups: list[tuple[str, ...]] = []
    for group_index, group in enumerate(dependency_groups):
        if not group:
            raise ValueError(f"{field_name}[{group_index}] must not be empty")
        normalized_group = tuple(str(member_id) for member_id in group)
        if len(normalized_group) != len(set(normalized_group)):
            raise ValueError(f"{field_name}[{group_index}] must not repeat ids")
        normalized_groups.append(normalized_group)
    return tuple(normalized_groups)


def _ensure_unique_ids(field_name: str, ids: tuple[str, ...]) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} ids must be unique")


@dataclass(frozen=True, slots=True)
class GlowPointSpec:
    """One glow-aware point instance.

    ``point_dependency_groups`` and ``line_dependency_groups`` both use OR-of-AND
    semantics:

    - each tuple item is one OR alternative
    - ids inside one group are AND-required together
    """

    point_id: str
    anchor_x: int
    anchor_y: int
    point_dependency_groups: GlowDependencyGroups = ()
    line_dependency_groups: GlowDependencyGroups = ()
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.point_id:
            raise ValueError("GlowPointSpec.point_id must not be empty")
        object.__setattr__(
            self,
            "point_dependency_groups",
            _normalize_dependency_groups(
                "GlowPointSpec.point_dependency_groups",
                self.point_dependency_groups,
            ),
        )
        object.__setattr__(
            self,
            "line_dependency_groups",
            _normalize_dependency_groups(
                "GlowPointSpec.line_dependency_groups",
                self.line_dependency_groups,
            ),
        )
        if self.display_name == "":
            raise ValueError("GlowPointSpec.display_name must not be empty when supplied")


@dataclass(frozen=True, slots=True)
class GlowLineAssetSpec:
    """One reusable cropped line sprite asset for glow export."""

    asset_id: str
    asset_name: str
    origin_x: int
    origin_y: int
    png_path: str | None = None

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("GlowLineAssetSpec.asset_id must not be empty")
        if not self.asset_name:
            raise ValueError("GlowLineAssetSpec.asset_name must not be empty")
        if self.png_path == "":
            raise ValueError("GlowLineAssetSpec.png_path must not be empty when supplied")


@dataclass(frozen=True, slots=True)
class GlowLineSpec:
    """One runtime glow line instance referencing one reusable sprite asset."""

    line_id: str
    asset_id: str
    anchor_x: int
    anchor_y: int
    draw_knot: bool = False
    point_dependency_groups: GlowDependencyGroups = ()
    line_dependency_groups: GlowDependencyGroups = ()

    def __post_init__(self) -> None:
        if not self.line_id:
            raise ValueError("GlowLineSpec.line_id must not be empty")
        if not self.asset_id:
            raise ValueError("GlowLineSpec.asset_id must not be empty")
        object.__setattr__(
            self,
            "point_dependency_groups",
            _normalize_dependency_groups(
                "GlowLineSpec.point_dependency_groups",
                self.point_dependency_groups,
            ),
        )
        object.__setattr__(
            self,
            "line_dependency_groups",
            _normalize_dependency_groups(
                "GlowLineSpec.line_dependency_groups",
                self.line_dependency_groups,
            ),
        )


@dataclass(frozen=True, slots=True)
class GlowExportManifest:
    """Generic export manifest for one solved tree's glow/background output."""

    tree_id: str
    point_specs: tuple[GlowPointSpec, ...]
    line_asset_specs: tuple[GlowLineAssetSpec, ...]
    line_specs: tuple[GlowLineSpec, ...]
    background_png_path: str | None = None

    def __post_init__(self) -> None:
        if not self.tree_id:
            raise ValueError("GlowExportManifest.tree_id must not be empty")
        if self.background_png_path == "":
            raise ValueError("GlowExportManifest.background_png_path must not be empty")

        point_ids = tuple(point.point_id for point in self.point_specs)
        asset_ids = tuple(asset.asset_id for asset in self.line_asset_specs)
        asset_names = tuple(asset.asset_name for asset in self.line_asset_specs)
        line_ids = tuple(line.line_id for line in self.line_specs)
        _ensure_unique_ids("GlowExportManifest.point_specs", point_ids)
        _ensure_unique_ids("GlowExportManifest.line_asset_specs", asset_ids)
        _ensure_unique_ids("GlowExportManifest.line_asset_specs.asset_name", asset_names)
        _ensure_unique_ids("GlowExportManifest.line_specs", line_ids)

        point_id_set = set(point_ids)
        line_id_set = set(line_ids)
        asset_id_set = set(asset_ids)

        for point in self.point_specs:
            for dependency_group in point.point_dependency_groups:
                for dependency_id in dependency_group:
                    if dependency_id not in point_id_set:
                        raise ValueError(
                            f"GlowPointSpec {point.point_id!r} depends on unknown point {dependency_id!r}"
                        )
            for dependency_group in point.line_dependency_groups:
                for dependency_id in dependency_group:
                    if dependency_id not in line_id_set:
                        raise ValueError(
                            f"GlowPointSpec {point.point_id!r} depends on unknown line {dependency_id!r}"
                        )

        for line in self.line_specs:
            if line.asset_id not in asset_id_set:
                raise ValueError(
                    f"GlowLineSpec {line.line_id!r} references unknown asset {line.asset_id!r}"
                )
            for dependency_group in line.point_dependency_groups:
                for dependency_id in dependency_group:
                    if dependency_id not in point_id_set:
                        raise ValueError(
                            f"GlowLineSpec {line.line_id!r} depends on unknown point {dependency_id!r}"
                        )
            for dependency_group in line.line_dependency_groups:
                for dependency_id in dependency_group:
                    if dependency_id not in line_id_set:
                        raise ValueError(
                            f"GlowLineSpec {line.line_id!r} depends on unknown line {dependency_id!r}"
                        )
