"""Explicit graph-content input schema for the current frozen v1 solver path.

This module defines the thinnest production content boundary that can feed the
current placement, routing, and runtime-snapshot layers without hand-built
test-only assembly.
"""

from __future__ import annotations

from dataclasses import dataclass

from toolsv2.solver_common import (
    LogicalYRailId,
    NodeId,
    PortId,
    RoutingPolicy,
    _ensure_unique_strings,
)


@dataclass(frozen=True, slots=True)
class GraphContentNode:
    """One explicit node instance in input content."""

    node_id: NodeId
    kind: str
    authored_tier_y_rail_id: LogicalYRailId | None = None
    allowed_y_rail_ids: tuple[LogicalYRailId, ...] | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("GraphContentNode.kind must not be empty")
        if self.authored_tier_y_rail_id is not None and self.allowed_y_rail_ids is not None:
            raise ValueError(
                "GraphContentNode must not set both authored_tier_y_rail_id and allowed_y_rail_ids"
            )


@dataclass(frozen=True, slots=True)
class GraphContentRouteRequirement:
    """One explicit route requirement with source/sink port allowances."""

    requirement_id: str
    source_node_id: NodeId
    sink_node_id: NodeId
    requirement_kind: str
    source_port_ids: tuple[PortId, ...]
    sink_port_ids: tuple[PortId, ...]

    def __post_init__(self) -> None:
        if not self.requirement_id:
            raise ValueError("GraphContentRouteRequirement.requirement_id must not be empty")
        if not self.requirement_kind:
            raise ValueError("GraphContentRouteRequirement.requirement_kind must not be empty")
        if not self.source_port_ids:
            raise ValueError("GraphContentRouteRequirement.source_port_ids must not be empty")
        if not self.sink_port_ids:
            raise ValueError("GraphContentRouteRequirement.sink_port_ids must not be empty")
        _ensure_unique_strings(
            "GraphContentRouteRequirement.source_port_ids",
            tuple(str(port_id) for port_id in self.source_port_ids),
        )
        _ensure_unique_strings(
            "GraphContentRouteRequirement.sink_port_ids",
            tuple(str(port_id) for port_id in self.sink_port_ids),
        )


@dataclass(frozen=True, slots=True)
class GraphContentPortAttachmentRequirement:
    """One explicit screening-time required attachment count for a node port."""

    node_id: NodeId
    port_id: PortId
    required_attachments: int = 1

    def __post_init__(self) -> None:
        if self.required_attachments < 0:
            raise ValueError(
                "GraphContentPortAttachmentRequirement.required_attachments must be non-negative"
            )


@dataclass(frozen=True, slots=True)
class GraphContentOrderedSameRowGroup:
    """One explicit same-row ordering group in content input."""

    ordered_node_ids: tuple[NodeId, ...]

    def __post_init__(self) -> None:
        if not self.ordered_node_ids:
            raise ValueError("GraphContentOrderedSameRowGroup.ordered_node_ids must not be empty")
        _ensure_unique_strings(
            "GraphContentOrderedSameRowGroup.ordered_node_ids",
            tuple(str(node_id) for node_id in self.ordered_node_ids),
        )


@dataclass(frozen=True, slots=True)
class GraphContentModel:
    """Minimal explicit graph-content input for the current solver path."""

    routing_policy: RoutingPolicy
    nodes: tuple[GraphContentNode, ...]
    route_requirements: tuple[GraphContentRouteRequirement, ...] = ()
    screening_port_requirements: tuple[GraphContentPortAttachmentRequirement, ...] = ()
    ordered_same_row_groups: tuple[GraphContentOrderedSameRowGroup, ...] = ()

    def __post_init__(self) -> None:
        _ensure_unique_strings(
            "GraphContentModel.nodes",
            tuple(str(node.node_id) for node in self.nodes),
        )
        _ensure_unique_strings(
            "GraphContentModel.route_requirements",
            tuple(requirement.requirement_id for requirement in self.route_requirements),
        )
        _ensure_unique_strings(
            "GraphContentModel.screening_port_requirements",
            tuple(
                f"{requirement.node_id}|{requirement.port_id}"
                for requirement in self.screening_port_requirements
            ),
        )

        grouped_node_ids = [
            str(node_id)
            for group in self.ordered_same_row_groups
            for node_id in group.ordered_node_ids
        ]
        _ensure_unique_strings(
            "GraphContentModel.ordered_same_row_groups",
            tuple(grouped_node_ids),
        )
