"""Visual/build profile contracts separate from logical solver schema.

This module defines the data-only visual/build contracts that later renderer
and geometry/build-feasibility layers can consume without pushing visual rules
back into the logical solver core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType, Protocol

from toolsv2.solver_common import (
    Attributes,
    CardinalDirection,
    LogicalXRailId,
    LogicalYRailId,
    PortId,
    RenderProfileKey,
    _ensure_unique_keys,
    _ensure_unique_strings,
)


VisualLayerId = NewType("VisualLayerId", str)
RenderTemplateKey = NewType("RenderTemplateKey", str)
ConnectionFamilyKey = NewType("ConnectionFamilyKey", str)
CompositionOperatorId = NewType("CompositionOperatorId", str)
ObjectFinalizerRuleId = NewType("ObjectFinalizerRuleId", str)
RenderTemplateKind = Literal["pixel_mask", "sprite_ref"]
ConnectionRuleKind = Literal["repeat_span", "local_connection_piece"]


DEFAULT_BACKGROUND_LAYER_ID = VisualLayerId("background")
DEFAULT_SHADOW_LAYER_ID = VisualLayerId("shadow")
DEFAULT_ROAD_LAYER_ID = VisualLayerId("road")
DEFAULT_OBJECT_BODY_LAYER_ID = VisualLayerId("object_body")
DEFAULT_OBJECT_FOREGROUND_LAYER_ID = VisualLayerId("object_foreground")

COMPOSITION_OVERWRITE = CompositionOperatorId("overwrite")
COMPOSITION_MAX_LIGHT = CompositionOperatorId("max_light")

FINALIZER_COMPOSE_LOCAL_BLOCK = ObjectFinalizerRuleId("compose_local_block")


class LogicalToRenderMapper(Protocol):
    """Stable logical-to-render-space contract for visual consumers.

    The mapping remains separate from logical profile construction. This
    contract is intentionally minimal and does not freeze canvas policy,
    camera policy, or exporter behavior.
    """

    def x_pixel_for(self, rail_id: LogicalXRailId) -> int:
        """Map one logical x rail to a render-space x coordinate."""

    def y_pixel_for(self, rail_id: LogicalYRailId) -> int:
        """Map one logical y rail to a render-space y coordinate."""


# Compatibility alias for existing naming in profile.py.
LogicalToPixelMapper = LogicalToRenderMapper


@dataclass(frozen=True, slots=True)
class LocalFootprint:
    """Local visual/build footprint around one object anchor.

    Local object coordinates are centered on the object anchor by default:
    ``(0, 0)`` is the anchor, ``+x`` points right, and ``+y`` points down.
    ``anchor_x`` / ``anchor_y`` are only needed when a profile wants the
    logical placement anchor to differ from that centered default.
    """

    width: int
    height: int
    anchor_x: int = 0
    anchor_y: int = 0
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("LocalFootprint.width must be positive")
        if self.height <= 0:
            raise ValueError("LocalFootprint.height must be positive")
        _ensure_unique_keys("LocalFootprint.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class PortGeometrySpec:
    """Visual/build geometry for one local object port.

    ``offset_x`` / ``offset_y`` are local coordinates relative to the object
    anchor using the centered render-space convention.
    """

    port_id: PortId
    offset_x: int
    offset_y: int
    attach_direction: CardinalDirection
    connection_family_keys: tuple[ConnectionFamilyKey, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "PortGeometrySpec.connection_family_keys",
            tuple(str(key) for key in self.connection_family_keys),
        )
        _ensure_unique_keys("PortGeometrySpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class InternalTransitionSpec:
    """One local build-feasible transition between two object ports."""

    from_port_id: PortId
    to_port_id: PortId
    connection_family_key: ConnectionFamilyKey
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.from_port_id == self.to_port_id:
            raise ValueError("InternalTransitionSpec requires distinct ports")
        _ensure_unique_keys("InternalTransitionSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class BuildGeometryProfile:
    """Data-only build geometry profile for one render-profile key."""

    profile_key: RenderProfileKey
    footprint: LocalFootprint
    ports: tuple[PortGeometrySpec, ...] = ()
    internal_transitions: tuple[InternalTransitionSpec, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        port_ids = tuple(str(port.port_id) for port in self.ports)
        _ensure_unique_strings("BuildGeometryProfile.ports", port_ids)
        port_id_set = {port.port_id for port in self.ports}
        for transition in self.internal_transitions:
            if transition.from_port_id not in port_id_set:
                raise ValueError("InternalTransitionSpec.from_port_id must exist in BuildGeometryProfile.ports")
            if transition.to_port_id not in port_id_set:
                raise ValueError("InternalTransitionSpec.to_port_id must exist in BuildGeometryProfile.ports")
        _ensure_unique_keys("BuildGeometryProfile.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderLayerSpec:
    """One visual output layer and its composition operator."""

    layer_id: VisualLayerId
    order: int
    composition_operator: CompositionOperatorId
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.order < 0:
            raise ValueError("RenderLayerSpec.order must be non-negative")
        _ensure_unique_keys("RenderLayerSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderTemplateSpec:
    """One generic render template referenced by style profiles."""

    template_key: RenderTemplateKey
    kind: RenderTemplateKind
    pixel_rows: tuple[tuple[int, ...], ...] = ()
    asset_ref: str | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.kind == "pixel_mask":
            if not self.pixel_rows:
                raise ValueError("pixel_mask RenderTemplateSpec requires pixel_rows")
            row_lengths = {len(row) for row in self.pixel_rows}
            if len(row_lengths) != 1:
                raise ValueError("RenderTemplateSpec.pixel_rows must be rectangular")
            if self.asset_ref is not None:
                raise ValueError("pixel_mask RenderTemplateSpec must not declare asset_ref")
        else:
            if self.asset_ref is None:
                raise ValueError("sprite_ref RenderTemplateSpec requires asset_ref")
            if self.pixel_rows:
                raise ValueError("sprite_ref RenderTemplateSpec must not declare pixel_rows")
        _ensure_unique_keys("RenderTemplateSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderTransformSpec:
    """Data-only transform applied to a render template instance."""

    quarter_turns_clockwise: int = 0
    mirror_x: bool = False
    mirror_y: bool = False
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.quarter_turns_clockwise not in (0, 1, 2, 3):
            raise ValueError("RenderTransformSpec.quarter_turns_clockwise must be 0..3")
        _ensure_unique_keys("RenderTransformSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderTemplateBinding:
    """One style-layer binding to a render template."""

    layer_id: VisualLayerId
    template_key: RenderTemplateKey
    offset_x: int = 0
    offset_y: int = 0
    transform: RenderTransformSpec = field(default_factory=RenderTransformSpec)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("RenderTemplateBinding.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class LocalConnectionTemplateSpec:
    """One undirected local-connection visual binding for a port pair."""

    port_ids: tuple[PortId, PortId]
    binding: RenderTemplateBinding
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if len(self.port_ids) != 2:
            raise ValueError("LocalConnectionTemplateSpec.port_ids must contain exactly two ports")
        if self.port_ids[0] == self.port_ids[1]:
            raise ValueError("LocalConnectionTemplateSpec requires distinct ports")
        _ensure_unique_keys("LocalConnectionTemplateSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class JunctionPatternOverrideSpec:
    """Optional data-only junction pattern override for future render upgrades.

    V1 junction rendering still uses per-connection piece composition only.
    This record freezes a data-only extension point so later T/cross overrides
    can be added through profile data rather than engine rewrites.
    """

    engaged_port_ids: tuple[PortId, ...]
    template_bindings: tuple[RenderTemplateBinding, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "JunctionPatternOverrideSpec.engaged_port_ids",
            tuple(str(port_id) for port_id in self.engaged_port_ids),
        )
        _ensure_unique_keys("JunctionPatternOverrideSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderStyleProfile:
    """Data-only render style profile for one render-profile key."""

    profile_key: RenderProfileKey
    template_bindings: tuple[RenderTemplateBinding, ...] = ()
    local_connection_templates: tuple[LocalConnectionTemplateSpec, ...] = ()
    connection_pattern_overrides: tuple[JunctionPatternOverrideSpec, ...] = ()
    finalizer_rule_id: ObjectFinalizerRuleId | None = None
    local_composition_operator: CompositionOperatorId | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "RenderStyleProfile.local_connection_templates",
            tuple(
                "|".join(sorted(str(port_id) for port_id in template.port_ids))
                for template in self.local_connection_templates
            ),
        )
        _ensure_unique_strings(
            "RenderStyleProfile.connection_pattern_overrides",
            tuple(
                "|".join(sorted(str(port_id) for port_id in override.engaged_port_ids))
                for override in self.connection_pattern_overrides
            ),
        )
        _ensure_unique_keys("RenderStyleProfile.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class ConnectionFamilyProfile:
    """Static build/render family data for one connection technology."""

    family_key: ConnectionFamilyKey
    rule_kind: ConnectionRuleKind
    shape_kind: str
    layer_id: VisualLayerId
    template_keys: tuple[RenderTemplateKey, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.rule_kind not in ("repeat_span", "local_connection_piece"):
            raise ValueError(
                "ConnectionFamilyProfile.rule_kind must be 'repeat_span' or 'local_connection_piece'"
            )
        if not self.shape_kind:
            raise ValueError("ConnectionFamilyProfile.shape_kind must be non-empty")
        _ensure_unique_strings(
            "ConnectionFamilyProfile.template_keys",
            tuple(str(template_key) for template_key in self.template_keys),
        )
        _ensure_unique_keys("ConnectionFamilyProfile.attributes", self.attributes)


class VisualProfileCatalog(Protocol):
    """Thin data-only lookup surface for visual/build profile data."""

    def build_geometry_profile(self, profile_key: RenderProfileKey) -> BuildGeometryProfile:
        """Return build geometry data for one render-profile key."""

    def render_style_profile(self, profile_key: RenderProfileKey) -> RenderStyleProfile:
        """Return render style data for one render-profile key."""

    def render_layer_spec(self, layer_id: VisualLayerId) -> RenderLayerSpec:
        """Return layer ordering/composition data for one layer id."""

    def render_template_spec(self, template_key: RenderTemplateKey) -> RenderTemplateSpec:
        """Return one concrete render template specification."""

    def connection_family_profile(
        self,
        family_key: ConnectionFamilyKey,
    ) -> ConnectionFamilyProfile:
        """Return one static connection-family profile."""


@dataclass(frozen=True, slots=True)
class StaticVisualProfileCatalog:
    """Immutable in-memory visual/build profile catalog."""

    build_geometry_profiles: tuple[BuildGeometryProfile, ...] = ()
    render_style_profiles: tuple[RenderStyleProfile, ...] = ()
    render_layers: tuple[RenderLayerSpec, ...] = ()
    render_templates: tuple[RenderTemplateSpec, ...] = ()
    connection_families: tuple[ConnectionFamilyProfile, ...] = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "StaticVisualProfileCatalog.build_geometry_profiles",
            tuple(str(profile.profile_key) for profile in self.build_geometry_profiles),
        )
        _ensure_unique_strings(
            "StaticVisualProfileCatalog.render_style_profiles",
            tuple(str(profile.profile_key) for profile in self.render_style_profiles),
        )
        _ensure_unique_strings(
            "StaticVisualProfileCatalog.render_layers",
            tuple(str(layer.layer_id) for layer in self.render_layers),
        )
        _ensure_unique_strings(
            "StaticVisualProfileCatalog.render_templates",
            tuple(str(template.template_key) for template in self.render_templates),
        )
        _ensure_unique_strings(
            "StaticVisualProfileCatalog.connection_families",
            tuple(str(profile.family_key) for profile in self.connection_families),
        )

    def build_geometry_profile(self, profile_key: RenderProfileKey) -> BuildGeometryProfile:
        for profile in self.build_geometry_profiles:
            if profile.profile_key == profile_key:
                return profile
        raise KeyError(f"Unknown build geometry profile_key: {profile_key}")

    def render_style_profile(self, profile_key: RenderProfileKey) -> RenderStyleProfile:
        for profile in self.render_style_profiles:
            if profile.profile_key == profile_key:
                return profile
        raise KeyError(f"Unknown render style profile_key: {profile_key}")

    def render_layer_spec(self, layer_id: VisualLayerId) -> RenderLayerSpec:
        for layer in self.render_layers:
            if layer.layer_id == layer_id:
                return layer
        raise KeyError(f"Unknown render layer_id: {layer_id}")

    def render_template_spec(self, template_key: RenderTemplateKey) -> RenderTemplateSpec:
        for template in self.render_templates:
            if template.template_key == template_key:
                return template
        raise KeyError(f"Unknown render template_key: {template_key}")

    def connection_family_profile(
        self,
        family_key: ConnectionFamilyKey,
    ) -> ConnectionFamilyProfile:
        for profile in self.connection_families:
            if profile.family_key == family_key:
                return profile
        raise KeyError(f"Unknown connection family_key: {family_key}")


DEFAULT_PLAIN_JUNCTION_PROFILE_KEY = RenderProfileKey("junction/plain")
DEFAULT_SKILL_FRAME_PROFILE_KEY = RenderProfileKey("node/skill_frame")
DEFAULT_AND_KNOT_PROFILE_KEY = RenderProfileKey("node/and_knot")
DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY = ConnectionFamilyKey("road_external_straight")
DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY = ConnectionFamilyKey("road_junction_piece")
# Backward-compatible alias for the current default external family.
DEFAULT_PLAIN_CONNECTION_FAMILY_KEY = DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY

DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY = RenderTemplateKey("node/skill_frame/body")
DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY = RenderTemplateKey("node/skill_frame/shadow")
DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY = RenderTemplateKey("node/and_knot/body")
DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY = RenderTemplateKey(
    "connection/external_straight/primitive"
)
DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY = RenderTemplateKey(
    "connection/junction_piece/corner_tr"
)
DEFAULT_EXTERNAL_STRAIGHT_HORIZONTAL_TEMPLATE_KEY = DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY
DEFAULT_EXTERNAL_STRAIGHT_VERTICAL_TEMPLATE_KEY = DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY


def build_v1_default_render_layers() -> tuple[RenderLayerSpec, ...]:
    """Return the shared absolute layer catalog for the current renderer plan."""

    return (
        RenderLayerSpec(
            layer_id=DEFAULT_BACKGROUND_LAYER_ID,
            order=0,
            composition_operator=COMPOSITION_OVERWRITE,
        ),
        RenderLayerSpec(
            layer_id=DEFAULT_SHADOW_LAYER_ID,
            order=1,
            composition_operator=COMPOSITION_OVERWRITE,
        ),
        RenderLayerSpec(
            layer_id=DEFAULT_ROAD_LAYER_ID,
            order=3,
            composition_operator=COMPOSITION_OVERWRITE,
        ),
        RenderLayerSpec(
            layer_id=DEFAULT_OBJECT_BODY_LAYER_ID,
            order=4,
            composition_operator=COMPOSITION_OVERWRITE,
        ),
        RenderLayerSpec(
            layer_id=DEFAULT_OBJECT_FOREGROUND_LAYER_ID,
            order=5,
            composition_operator=COMPOSITION_OVERWRITE,
        ),
    )


def build_v1_plain_junction_visual_profile_catalog() -> StaticVisualProfileCatalog:
    """Return the minimal visual/build catalog for the default plain junction.

    This is the stable v1 build-geometry source for the current runtime
    junction substrate. It intentionally keeps render style/template data
    minimal because geometry/build-feasibility only needs the build geometry
    contract at this stage.
    """

    ports = (
        PortGeometrySpec(
            port_id=PortId("north"),
            offset_x=0,
            offset_y=-2,
            attach_direction="north",
            connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("south"),
            offset_x=0,
            offset_y=2,
            attach_direction="south",
            connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("west"),
            offset_x=-2,
            offset_y=0,
            attach_direction="west",
            connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("east"),
            offset_x=2,
            offset_y=0,
            attach_direction="east",
            connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
        ),
    )
    transitions = tuple(
        InternalTransitionSpec(
            from_port_id=from_port.port_id,
            to_port_id=to_port.port_id,
            connection_family_key=DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
        )
        for from_port in ports
        for to_port in ports
        if from_port.port_id != to_port.port_id
    )
    from toolsv2.source_art_catalog import build_v1_source_render_templates

    return StaticVisualProfileCatalog(
        build_geometry_profiles=(
            BuildGeometryProfile(
                profile_key=DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
                footprint=LocalFootprint(width=5, height=5),
                ports=ports,
                internal_transitions=transitions,
            ),
        ),
        render_style_profiles=(
            RenderStyleProfile(
                profile_key=DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
                finalizer_rule_id=FINALIZER_COMPOSE_LOCAL_BLOCK,
                local_composition_operator=COMPOSITION_MAX_LIGHT,
                local_connection_templates=(
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("north"), PortId("south")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                        ),
                    ),
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("west"), PortId("east")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                            transform=RenderTransformSpec(quarter_turns_clockwise=1),
                        ),
                    ),
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("north"), PortId("east")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
                        ),
                    ),
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("south"), PortId("east")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
                            transform=RenderTransformSpec(quarter_turns_clockwise=1),
                        ),
                    ),
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("south"), PortId("west")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
                            transform=RenderTransformSpec(quarter_turns_clockwise=2),
                        ),
                    ),
                    LocalConnectionTemplateSpec(
                        port_ids=(PortId("north"), PortId("west")),
                        binding=RenderTemplateBinding(
                            layer_id=DEFAULT_ROAD_LAYER_ID,
                            template_key=DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
                            transform=RenderTransformSpec(quarter_turns_clockwise=3),
                        ),
                    ),
                ),
            ),
        ),
        render_layers=build_v1_default_render_layers(),
        render_templates=build_v1_source_render_templates(),
        connection_families=(
            ConnectionFamilyProfile(
                family_key=DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
                rule_kind="repeat_span",
                shape_kind="axis_aligned_straight",
                layer_id=DEFAULT_ROAD_LAYER_ID,
                template_keys=(DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,),
            ),
            ConnectionFamilyProfile(
                family_key=DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
                rule_kind="local_connection_piece",
                shape_kind="local_connection_piece",
                layer_id=DEFAULT_ROAD_LAYER_ID,
            ),
        ),
    )


def build_v1_skill_frame_build_geometry_profile(
    *,
    top_port_id: PortId,
    bottom_port_id: PortId,
    profile_key: RenderProfileKey = DEFAULT_SKILL_FRAME_PROFILE_KEY,
) -> BuildGeometryProfile:
    """Return the centered build-geometry profile for the current skill frame."""

    return BuildGeometryProfile(
        profile_key=profile_key,
        footprint=LocalFootprint(width=31, height=31),
        ports=(
            PortGeometrySpec(
                port_id=top_port_id,
                offset_x=0,
                offset_y=-15,
                attach_direction="north",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
            PortGeometrySpec(
                port_id=bottom_port_id,
                offset_x=0,
                offset_y=14,
                attach_direction="south",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
        ),
    )


def build_v1_skill_frame_render_style_profile(
    profile_key: RenderProfileKey = DEFAULT_SKILL_FRAME_PROFILE_KEY,
) -> RenderStyleProfile:
    """Return the v1 skill-frame render style profile."""

    return RenderStyleProfile(
        profile_key=profile_key,
        template_bindings=(
            RenderTemplateBinding(
                layer_id=DEFAULT_SHADOW_LAYER_ID,
                template_key=DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
                offset_y=15,
            ),
            RenderTemplateBinding(
                layer_id=DEFAULT_OBJECT_BODY_LAYER_ID,
                template_key=DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
            ),
        ),
    )


def build_v1_and_knot_build_geometry_profile(
    *,
    top_port_id: PortId,
    left_port_id: PortId,
    right_port_id: PortId,
    bottom_port_id: PortId,
    profile_key: RenderProfileKey = DEFAULT_AND_KNOT_PROFILE_KEY,
) -> BuildGeometryProfile:
    """Return the centered build-geometry profile for the current AND knot."""

    return BuildGeometryProfile(
        profile_key=profile_key,
        footprint=LocalFootprint(width=5, height=7),
        ports=(
            PortGeometrySpec(
                port_id=top_port_id,
                offset_x=0,
                offset_y=-2,
                attach_direction="north",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
            PortGeometrySpec(
                port_id=left_port_id,
                offset_x=-1,
                offset_y=0,
                attach_direction="west",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
            PortGeometrySpec(
                port_id=right_port_id,
                offset_x=1,
                offset_y=0,
                attach_direction="east",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
            PortGeometrySpec(
                port_id=bottom_port_id,
                offset_x=0,
                offset_y=2,
                attach_direction="south",
                connection_family_keys=(DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,),
            ),
        ),
    )


def build_v1_and_knot_render_style_profile(
    profile_key: RenderProfileKey = DEFAULT_AND_KNOT_PROFILE_KEY,
) -> RenderStyleProfile:
    """Return the v1 AND-knot render style profile."""

    return RenderStyleProfile(
        profile_key=profile_key,
        template_bindings=(
            RenderTemplateBinding(
                layer_id=DEFAULT_OBJECT_BODY_LAYER_ID,
                template_key=DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
            ),
        ),
    )


def build_v1_core_render_templates() -> tuple[RenderTemplateSpec, ...]:
    """Return the current symbolic render-template catalog for core object families.

    This compatibility helper delegates to the external source-art catalog so
    art-file layout changes do not require edits to this generic profile module.
    """

    from toolsv2.source_art_catalog import build_v1_source_render_templates

    return build_v1_source_render_templates()


def build_v1_core_visual_profile_catalog(
    *,
    skill_frame_top_port_id: PortId,
    skill_frame_bottom_port_id: PortId,
    and_knot_top_port_id: PortId,
    and_knot_left_port_id: PortId,
    and_knot_right_port_id: PortId,
    and_knot_bottom_port_id: PortId,
) -> StaticVisualProfileCatalog:
    """Return the current concrete v1 visual/build catalog for core object families.

    Node-port ids remain caller-supplied because logical node definitions are
    still the source of truth for port identity. The centered local geometry,
    shared layer ordering, and current straight-road connection family are
    frozen here without forcing a schema-side port-id convention.
    """

    junction_catalog = build_v1_plain_junction_visual_profile_catalog()
    return StaticVisualProfileCatalog(
        build_geometry_profiles=(
            junction_catalog.build_geometry_profiles[0],
            build_v1_skill_frame_build_geometry_profile(
                top_port_id=skill_frame_top_port_id,
                bottom_port_id=skill_frame_bottom_port_id,
            ),
            build_v1_and_knot_build_geometry_profile(
                top_port_id=and_knot_top_port_id,
                left_port_id=and_knot_left_port_id,
                right_port_id=and_knot_right_port_id,
                bottom_port_id=and_knot_bottom_port_id,
            ),
        ),
        render_style_profiles=(
            junction_catalog.render_style_profiles[0],
            build_v1_skill_frame_render_style_profile(),
            build_v1_and_knot_render_style_profile(),
        ),
        render_layers=build_v1_default_render_layers(),
        render_templates=build_v1_core_render_templates(),
        connection_families=junction_catalog.connection_families,
    )
