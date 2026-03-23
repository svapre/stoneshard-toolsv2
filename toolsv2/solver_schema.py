"""Schema and definition layer for solver objects.

These types describe object capabilities and metadata. They are separate from
runtime occupancy, connectivity, and route state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from toolsv2.solver_common import (
    Attributes,
    CardinalDirection,
    Junction,
    NodeId,
    PortId,
    RenderProfileKey,
    _ensure_unique_keys,
    _ensure_unique_strings,
)


@dataclass(frozen=True, slots=True)
class RenderProfileRef:
    """Optional render-profile reference for one logical element.

    This is metadata only. ``None`` means the logical element is not rendered.
    The renderer remains separate from solver core logic.
    """

    profile_key: RenderProfileKey | None = None
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_keys("RenderProfileRef.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class PortDefinition:
    """A schema-level node port definition."""

    port_id: PortId
    orientation: CardinalDirection
    capacity: int
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.capacity < 0:
            raise ValueError("PortDefinition.capacity must be non-negative")
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("PortDefinition.render_profile must be RenderProfileRef")
        _ensure_unique_keys("PortDefinition.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    """A generic schema-level node definition."""

    node_id: NodeId
    kind: str
    ports: tuple[PortDefinition, ...]
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        port_ids = tuple(str(port.port_id) for port in self.ports)
        _ensure_unique_strings("NodeDefinition.ports", port_ids)
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("NodeDefinition.render_profile must be RenderProfileRef")
        _ensure_unique_keys("NodeDefinition.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class JunctionDefinition:
    """Schema-level static data for a junction."""

    junction: Junction
    allows_node_occupancy: bool = True
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("JunctionDefinition.render_profile must be RenderProfileRef")
        _ensure_unique_keys("JunctionDefinition.attributes", self.attributes)
