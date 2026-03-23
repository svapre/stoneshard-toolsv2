"""Visual/build profile contracts separate from logical solver schema.

This module defines the data-only visual/build contracts that later renderer
and geometry/build-feasibility layers can consume without pushing visual rules
back into the logical solver core.
"""

from __future__ import annotations

from dataclasses import dataclass
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
RenderTemplateKind = Literal["pixel_mask", "sprite_ref"]


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
    """Local visual/build footprint around one object anchor."""

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
    """Visual/build geometry for one local object port."""

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
class RenderTemplateBinding:
    """One style-layer binding to a render template."""

    layer_id: VisualLayerId
    template_key: RenderTemplateKey
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("RenderTemplateBinding.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RenderStyleProfile:
    """Data-only render style profile for one render-profile key."""

    profile_key: RenderProfileKey
    template_bindings: tuple[RenderTemplateBinding, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("RenderStyleProfile.attributes", self.attributes)


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


@dataclass(frozen=True, slots=True)
class StaticVisualProfileCatalog:
    """Immutable in-memory visual/build profile catalog."""

    build_geometry_profiles: tuple[BuildGeometryProfile, ...] = ()
    render_style_profiles: tuple[RenderStyleProfile, ...] = ()
    render_layers: tuple[RenderLayerSpec, ...] = ()
    render_templates: tuple[RenderTemplateSpec, ...] = ()

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


DEFAULT_PLAIN_JUNCTION_PROFILE_KEY = RenderProfileKey("junction/plain")
DEFAULT_PLAIN_CONNECTION_FAMILY_KEY = ConnectionFamilyKey("road_basic")


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
            offset_x=2,
            offset_y=0,
            attach_direction="north",
            connection_family_keys=(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("south"),
            offset_x=2,
            offset_y=4,
            attach_direction="south",
            connection_family_keys=(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("west"),
            offset_x=0,
            offset_y=2,
            attach_direction="west",
            connection_family_keys=(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,),
        ),
        PortGeometrySpec(
            port_id=PortId("east"),
            offset_x=4,
            offset_y=2,
            attach_direction="east",
            connection_family_keys=(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,),
        ),
    )
    transitions = tuple(
        InternalTransitionSpec(
            from_port_id=from_port.port_id,
            to_port_id=to_port.port_id,
            connection_family_key=DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,
        )
        for from_port in ports
        for to_port in ports
        if from_port.port_id != to_port.port_id
    )
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
            ),
        ),
    )
