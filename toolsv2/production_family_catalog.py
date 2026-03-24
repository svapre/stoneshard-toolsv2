"""Data-only production node-family catalog.

This module isolates current family-specific node-definition wiring from the
generic loader so new families can be added by catalog extension rather than
core-loader edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.solver_common import NodeId, PortId
from toolsv2.solver_schema import NodeDefinition, PortDefinition, RenderProfileRef
from toolsv2.visual_profiles import (
    DEFAULT_AND_KNOT_PROFILE_KEY,
    DEFAULT_SKILL_FRAME_PROFILE_KEY,
)


V1_SKILL_FRAME_KIND = "skill_frame"
V1_AND_KNOT_KIND = "and_knot"

V1_SKILL_FRAME_TOP_PORT_ID = PortId("top")
V1_SKILL_FRAME_BOTTOM_PORT_ID = PortId("bottom")

V1_AND_KNOT_TOP_PORT_ID = PortId("top")
V1_AND_KNOT_LEFT_PORT_ID = PortId("left")
V1_AND_KNOT_RIGHT_PORT_ID = PortId("right")
V1_AND_KNOT_BOTTOM_PORT_ID = PortId("bottom")


@dataclass(frozen=True, slots=True)
class NodeFamilyPortSpec:
    """One data-only schema port template for a node family."""

    port_id: PortId
    orientation: str
    capacity: int | None = None
    render_profile: RenderProfileRef = RenderProfileRef()
    attributes: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def build_port_definition(self) -> PortDefinition:
        return PortDefinition(
            port_id=self.port_id,
            orientation=self.orientation,  # type: ignore[arg-type]
            capacity=self.capacity,
            render_profile=self.render_profile,
            attributes=self.attributes,
        )


@dataclass(frozen=True, slots=True)
class ProductionNodeFamilySpec:
    """One data-only production node family."""

    kind: str
    render_profile: RenderProfileRef
    ports: tuple[NodeFamilyPortSpec, ...]
    attributes: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def build_node_definition(self, node_id: NodeId) -> NodeDefinition:
        return NodeDefinition(
            node_id=node_id,
            kind=self.kind,
            ports=tuple(port.build_port_definition() for port in self.ports),
            render_profile=self.render_profile,
            attributes=self.attributes,
        )


@dataclass(frozen=True, slots=True)
class ProductionNodeFamilyCatalog:
    """Immutable kind -> family-spec mapping."""

    families_by_kind: Mapping[str, ProductionNodeFamilySpec]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "families_by_kind",
            MappingProxyType(dict(self.families_by_kind)),
        )

    def family_spec(self, kind: str) -> ProductionNodeFamilySpec:
        try:
            return self.families_by_kind[kind]
        except KeyError as exc:
            raise KeyError(f"Unknown production node family kind: {kind}") from exc


def build_v1_production_node_family_catalog() -> ProductionNodeFamilyCatalog:
    """Return the current production family catalog."""

    return ProductionNodeFamilyCatalog(
        families_by_kind={
            V1_SKILL_FRAME_KIND: ProductionNodeFamilySpec(
                kind=V1_SKILL_FRAME_KIND,
                render_profile=RenderProfileRef(profile_key=DEFAULT_SKILL_FRAME_PROFILE_KEY),
                ports=(
                    NodeFamilyPortSpec(
                        port_id=V1_SKILL_FRAME_TOP_PORT_ID,
                        orientation="north",
                    ),
                    NodeFamilyPortSpec(
                        port_id=V1_SKILL_FRAME_BOTTOM_PORT_ID,
                        orientation="south",
                    ),
                ),
            ),
            V1_AND_KNOT_KIND: ProductionNodeFamilySpec(
                kind=V1_AND_KNOT_KIND,
                render_profile=RenderProfileRef(profile_key=DEFAULT_AND_KNOT_PROFILE_KEY),
                ports=(
                    NodeFamilyPortSpec(
                        port_id=V1_AND_KNOT_TOP_PORT_ID,
                        orientation="north",
                        capacity=1,
                    ),
                    NodeFamilyPortSpec(
                        port_id=V1_AND_KNOT_LEFT_PORT_ID,
                        orientation="west",
                        capacity=1,
                    ),
                    NodeFamilyPortSpec(
                        port_id=V1_AND_KNOT_RIGHT_PORT_ID,
                        orientation="east",
                        capacity=1,
                    ),
                    NodeFamilyPortSpec(
                        port_id=V1_AND_KNOT_BOTTOM_PORT_ID,
                        orientation="south",
                    ),
                ),
            ),
        }
    )
