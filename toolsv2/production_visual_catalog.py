"""Data-only production visual-family catalog.

This module isolates current family-specific visual/build registration from the
generic profile contract layer so new families can be added without editing
generic renderer/profile modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.production_family_catalog import (
    V1_AND_KNOT_BOTTOM_PORT_ID,
    V1_AND_KNOT_LEFT_PORT_ID,
    V1_AND_KNOT_RIGHT_PORT_ID,
    V1_AND_KNOT_TOP_PORT_ID,
    V1_SKILL_FRAME_BOTTOM_PORT_ID,
    V1_SKILL_FRAME_TOP_PORT_ID,
)
from toolsv2.source_art_catalog import build_v1_source_render_templates
from toolsv2.solver_common import RenderProfileKey
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    DEFAULT_AND_KNOT_PROFILE_KEY,
    DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
    DEFAULT_SKILL_FRAME_PROFILE_KEY,
    RenderStyleProfile,
    StaticVisualProfileCatalog,
    build_v1_and_knot_build_geometry_profile,
    build_v1_and_knot_render_style_profile,
    build_v1_default_render_layers,
    build_v1_plain_junction_visual_profile_catalog,
    build_v1_skill_frame_build_geometry_profile,
    build_v1_skill_frame_render_style_profile,
)


@dataclass(frozen=True, slots=True)
class ProductionVisualFamilySpec:
    """One data-only visual/build family registration."""

    profile_key: RenderProfileKey
    build_geometry_profile: BuildGeometryProfile
    render_style_profile: RenderStyleProfile


@dataclass(frozen=True, slots=True)
class ProductionVisualFamilyCatalog:
    """Immutable render-profile-key -> visual family spec mapping."""

    families_by_profile_key: Mapping[RenderProfileKey, ProductionVisualFamilySpec]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "families_by_profile_key",
            MappingProxyType(dict(self.families_by_profile_key)),
        )

    def family_spec(self, profile_key: RenderProfileKey) -> ProductionVisualFamilySpec:
        try:
            return self.families_by_profile_key[profile_key]
        except KeyError as exc:
            raise KeyError(
                f"Unknown production visual family profile_key: {profile_key}"
            ) from exc

    def family_specs(self) -> tuple[ProductionVisualFamilySpec, ...]:
        return tuple(self.families_by_profile_key.values())


def build_v1_production_visual_family_catalog() -> ProductionVisualFamilyCatalog:
    """Return the current production visual/build family catalog."""

    skill_frame_spec = ProductionVisualFamilySpec(
        profile_key=DEFAULT_SKILL_FRAME_PROFILE_KEY,
        build_geometry_profile=build_v1_skill_frame_build_geometry_profile(
            top_port_id=V1_SKILL_FRAME_TOP_PORT_ID,
            bottom_port_id=V1_SKILL_FRAME_BOTTOM_PORT_ID,
        ),
        render_style_profile=build_v1_skill_frame_render_style_profile(),
    )
    and_knot_spec = ProductionVisualFamilySpec(
        profile_key=DEFAULT_AND_KNOT_PROFILE_KEY,
        build_geometry_profile=build_v1_and_knot_build_geometry_profile(
            top_port_id=V1_AND_KNOT_TOP_PORT_ID,
            left_port_id=V1_AND_KNOT_LEFT_PORT_ID,
            right_port_id=V1_AND_KNOT_RIGHT_PORT_ID,
            bottom_port_id=V1_AND_KNOT_BOTTOM_PORT_ID,
        ),
        render_style_profile=build_v1_and_knot_render_style_profile(),
    )
    return ProductionVisualFamilyCatalog(
        families_by_profile_key={
            skill_frame_spec.profile_key: skill_frame_spec,
            and_knot_spec.profile_key: and_knot_spec,
        }
    )


def build_v1_production_visual_profile_catalog() -> StaticVisualProfileCatalog:
    """Return the current production visual/build catalog."""

    junction_catalog = build_v1_plain_junction_visual_profile_catalog()
    family_catalog = build_v1_production_visual_family_catalog()
    family_specs = family_catalog.family_specs()
    return StaticVisualProfileCatalog(
        build_geometry_profiles=(
            junction_catalog.build_geometry_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY),
            *(spec.build_geometry_profile for spec in family_specs),
        ),
        render_style_profiles=(
            junction_catalog.render_style_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY),
            *(spec.render_style_profile for spec in family_specs),
        ),
        render_layers=build_v1_default_render_layers(),
        render_templates=build_v1_source_render_templates(),
        connection_families=junction_catalog.connection_families,
    )
