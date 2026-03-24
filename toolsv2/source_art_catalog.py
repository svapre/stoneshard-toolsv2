"""Data-only source-art catalog for current production render templates.

This module isolates source-art file layout from generic visual/build profile
logic so future asset moves do not require core renderer/profile edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.visual_profiles import (
    DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
    RenderTemplateKey,
    RenderTemplateSpec,
)


@dataclass(frozen=True, slots=True)
class SourceArtCatalog:
    """Immutable template-key -> source-art-path catalog."""

    asset_refs_by_template_key: Mapping[RenderTemplateKey, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "asset_refs_by_template_key",
            MappingProxyType(dict(self.asset_refs_by_template_key)),
        )

    def asset_ref_for(self, template_key: RenderTemplateKey) -> str:
        try:
            return self.asset_refs_by_template_key[template_key]
        except KeyError as exc:
            raise KeyError(f"Unknown source-art template key: {template_key}") from exc


def build_v1_source_art_catalog() -> SourceArtCatalog:
    """Return the current object-grouped source-art catalog."""

    return SourceArtCatalog(
        asset_refs_by_template_key={
            DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY: "art/source/node/skill_frame/FRAME_ROOT.png",
            DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY: "art/source/node/skill_frame/FRAME_ROOT_SHADOW.png",
            DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY: "art/source/node/and_knot/GATE_AND.png",
            DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY: "art/source/connection/external_straight/NONDIR_PORTS_TB.png",
            DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY: "art/source/connection/junction_piece/DIR_PORTS_TR_IN_T_OUT_R.png",
        }
    )


def build_v1_source_render_templates() -> tuple[RenderTemplateSpec, ...]:
    """Return sprite-ref template specs sourced entirely from the art catalog."""

    source_art_catalog = build_v1_source_art_catalog()
    return tuple(
        RenderTemplateSpec(
            template_key=template_key,
            kind="sprite_ref",
            asset_ref=source_art_catalog.asset_ref_for(template_key),
        )
        for template_key in (
            DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
            DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
            DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
            DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
            DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
        )
    )
