"""Renderer-side contracts separate from runtime truth and visual profiles.

This module freezes the boundary between:
- committed runtime source-of-truth state
- render resolution / projection
- primitive expansion
- final rendering/composition

It intentionally does not implement pixel output yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from toolsv2.solver_common import (
    Attributes,
    CardinalDirection,
    ObjectRef,
    PortEdgeId,
    PortId,
    RenderProfileKey,
    _ensure_unique_keys,
    _ensure_unique_strings,
)
from toolsv2.solver_runtime import PortGraphState
from toolsv2.visual_profiles import (
    CompositionOperatorId,
    ConnectionFamilyKey,
    LogicalToRenderMapper,
    RenderTransformSpec,
    RenderTemplateKey,
    VisualLayerId,
    VisualProfileCatalog,
)


RenderInstanceRef = ObjectRef | PortEdgeId


@dataclass(frozen=True, slots=True)
class ResolvedPortRenderSpec:
    """One port resolved into render-space coordinates."""

    port_id: PortId
    pixel_x: int
    pixel_y: int
    attach_direction: CardinalDirection
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("ResolvedPortRenderSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class ResolvedLocalConnectionSpec:
    """One resolved local connection inside a single renderable object."""

    from_port_id: PortId
    to_port_id: PortId
    connection_family_key: ConnectionFamilyKey
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.from_port_id == self.to_port_id:
            raise ValueError("ResolvedLocalConnectionSpec requires distinct ports")
        _ensure_unique_keys("ResolvedLocalConnectionSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class ResolvedSpanSpec:
    """One resolved dynamic span such as an external edge run."""

    connection_family_key: ConnectionFamilyKey
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.start_x == self.end_x and self.start_y == self.end_y:
            raise ValueError("ResolvedSpanSpec requires distinct endpoints")
        _ensure_unique_keys("ResolvedSpanSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class ResolvedObjectRenderSpec:
    """One render-ready object instance with dynamic state already resolved."""

    instance_ref: RenderInstanceRef
    profile_key: RenderProfileKey
    anchor_x: int
    anchor_y: int
    ports: tuple[ResolvedPortRenderSpec, ...] = ()
    local_connections: tuple[ResolvedLocalConnectionSpec, ...] = ()
    spans: tuple[ResolvedSpanSpec, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "ResolvedObjectRenderSpec.ports",
            tuple(str(port.port_id) for port in self.ports),
        )
        _ensure_unique_keys("ResolvedObjectRenderSpec.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class SpriteStampInstruction:
    """One generic sprite placement instruction."""

    layer_id: VisualLayerId
    template_key: RenderTemplateKey
    anchor_x: int
    anchor_y: int
    transform: RenderTransformSpec = RenderTransformSpec()
    composition_operator: CompositionOperatorId | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("SpriteStampInstruction.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class PixelMaskStampInstruction:
    """One generic pixel-mask placement instruction."""

    layer_id: VisualLayerId
    template_key: RenderTemplateKey
    origin_x: int
    origin_y: int
    transform: RenderTransformSpec = RenderTransformSpec()
    composition_operator: CompositionOperatorId | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("PixelMaskStampInstruction.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RepeatedSpanInstruction:
    """One generic repeated-span draw instruction."""

    layer_id: VisualLayerId
    connection_family_key: ConnectionFamilyKey
    template_key: RenderTemplateKey
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    transform: RenderTransformSpec = RenderTransformSpec()
    composition_operator: CompositionOperatorId | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.start_x == self.end_x and self.start_y == self.end_y:
            raise ValueError("RepeatedSpanInstruction requires distinct endpoints")
        _ensure_unique_keys("RepeatedSpanInstruction.attributes", self.attributes)


RenderInstruction = (
    SpriteStampInstruction
    | PixelMaskStampInstruction
    | RepeatedSpanInstruction
)


class RenderResolver(Protocol):
    """Resolve committed runtime truth into render-ready object specs."""

    def __call__(
        self,
        state: PortGraphState,
        mapper: LogicalToRenderMapper,
        visual_profile_catalog: VisualProfileCatalog,
    ) -> tuple[ResolvedObjectRenderSpec, ...]:
        """Return render-ready object specs with dynamic visual data resolved."""


class PrimitiveExpander(Protocol):
    """Expand resolved object specs into generic renderer instructions."""

    def __call__(
        self,
        resolved_objects: tuple[ResolvedObjectRenderSpec, ...],
        visual_profile_catalog: VisualProfileCatalog,
    ) -> tuple[RenderInstruction, ...]:
        """Return neutral render instructions only."""
