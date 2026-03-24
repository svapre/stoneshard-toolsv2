"""Thin production definitions loader for the current frozen v1 object set.

This module converts explicit content/schema input into the canonical current
production node definitions, route requirements, placement metadata, and the
shared visual profile catalog used by geometry and later render layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.domain_builder import NodePlacementMetadata, OrderedSameRowGroup
from toolsv2.eligibility import RouteRequirementPortAllowance, StaticRouteRequirementSchemaView
from toolsv2.graph_content import (
    GraphContentModel,
    GraphContentNode,
    GraphContentOrderedSameRowGroup,
    GraphContentPortAttachmentRequirement,
    GraphContentRouteRequirement,
)
from toolsv2.production_family_catalog import build_v1_production_node_family_catalog
from toolsv2.production_node_definitions import (
    build_v1_production_visual_profile_catalog,
)
from toolsv2.screening import PortAttachmentRequirement
from toolsv2.solver_common import NodeId, PortId, RouteRequirement, RoutingPolicy
from toolsv2.solver_schema import NodeDefinition
from toolsv2.visual_profiles import StaticVisualProfileCatalog


@dataclass(frozen=True, slots=True)
class LoadedDefinitions:
    """Loaded production definitions for the current frozen v1 family set."""

    node_definitions: Mapping[NodeId, NodeDefinition]
    visual_profile_catalog: StaticVisualProfileCatalog

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "node_definitions",
            MappingProxyType(dict(self.node_definitions)),
        )
        if not isinstance(self.visual_profile_catalog, StaticVisualProfileCatalog):
            raise TypeError("visual_profile_catalog must be StaticVisualProfileCatalog")


@dataclass(frozen=True, slots=True)
class LoadedGraphContent:
    """Loaded graph-content data ready for current placement and routing layers."""

    node_definitions: Mapping[NodeId, NodeDefinition]
    visual_profile_catalog: StaticVisualProfileCatalog
    node_metadata: tuple[NodePlacementMetadata, ...]
    ordered_same_row_groups: tuple[OrderedSameRowGroup, ...]
    route_requirements: tuple[RouteRequirement, ...]
    schema_view: StaticRouteRequirementSchemaView
    port_requirements_by_node_id: Mapping[NodeId, tuple[PortAttachmentRequirement, ...]]
    routing_policy: RoutingPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "node_definitions",
            MappingProxyType(dict(self.node_definitions)),
        )
        object.__setattr__(
            self,
            "port_requirements_by_node_id",
            MappingProxyType(
                {
                    node_id: tuple(requirements)
                    for node_id, requirements in self.port_requirements_by_node_id.items()
                }
            ),
        )
        if not isinstance(self.visual_profile_catalog, StaticVisualProfileCatalog):
            raise TypeError("visual_profile_catalog must be StaticVisualProfileCatalog")
        if not isinstance(self.schema_view, StaticRouteRequirementSchemaView):
            raise TypeError("schema_view must be StaticRouteRequirementSchemaView")


def load_v1_production_definitions(
    node_kinds_by_node_id: Mapping[NodeId, str],
) -> LoadedDefinitions:
    """Load the current frozen v1 production node definitions.

    Supported kinds come from the external production family catalog.
    """

    family_catalog = build_v1_production_node_family_catalog()
    node_definitions: dict[NodeId, NodeDefinition] = {}

    for node_id in sorted(node_kinds_by_node_id, key=str):
        kind = node_kinds_by_node_id[node_id]
        try:
            family_spec = family_catalog.family_spec(kind)
        except KeyError as exc:
            raise ValueError(
                f"Unknown v1 production node kind {kind!r} for node {node_id!r}"
            ) from exc
        node_definitions[node_id] = family_spec.build_node_definition(node_id)

    return LoadedDefinitions(
        node_definitions=node_definitions,
        visual_profile_catalog=build_v1_production_visual_profile_catalog(),
    )


def _node_kind_lookup(content: GraphContentModel) -> dict[NodeId, str]:
    return {
        node.node_id: node.kind
        for node in content.nodes
    }


def _node_metadata(node: GraphContentNode) -> NodePlacementMetadata:
    return NodePlacementMetadata(
        node_id=node.node_id,
        authored_tier_y_rail_id=node.authored_tier_y_rail_id,
        allowed_y_rail_ids=node.allowed_y_rail_ids,
    )


def _same_row_group(group: GraphContentOrderedSameRowGroup) -> OrderedSameRowGroup:
    return OrderedSameRowGroup(ordered_node_ids=group.ordered_node_ids)


def _route_requirement(spec: GraphContentRouteRequirement) -> RouteRequirement:
    return RouteRequirement(
        requirement_id=spec.requirement_id,
        source_object_ref=spec.source_node_id,
        sink_object_ref=spec.sink_node_id,
        requirement_kind=spec.requirement_kind,
    )


def _build_schema_view(
    route_requirements: tuple[GraphContentRouteRequirement, ...],
) -> StaticRouteRequirementSchemaView:
    return StaticRouteRequirementSchemaView(
        source_allowances=tuple(
            RouteRequirementPortAllowance(
                object_ref=requirement.source_node_id,
                requirement_kind=requirement.requirement_kind,
                requirement_id=requirement.requirement_id,
                port_local_keys=tuple(requirement.source_port_ids),
            )
            for requirement in sorted(
                route_requirements,
                key=lambda item: (
                    str(item.source_node_id),
                    item.requirement_kind,
                    item.requirement_id,
                ),
            )
        ),
        sink_allowances=tuple(
            RouteRequirementPortAllowance(
                object_ref=requirement.sink_node_id,
                requirement_kind=requirement.requirement_kind,
                requirement_id=requirement.requirement_id,
                port_local_keys=tuple(requirement.sink_port_ids),
            )
            for requirement in sorted(
                route_requirements,
                key=lambda item: (
                    str(item.sink_node_id),
                    item.requirement_kind,
                    item.requirement_id,
                ),
            )
        ),
    )


def _build_port_requirements_by_node_id(
    requirements: tuple[GraphContentPortAttachmentRequirement, ...],
) -> dict[NodeId, tuple[PortAttachmentRequirement, ...]]:
    grouped: dict[NodeId, list[PortAttachmentRequirement]] = {}
    for requirement in requirements:
        grouped.setdefault(requirement.node_id, []).append(
            PortAttachmentRequirement(
                port_id=requirement.port_id,
                required_attachments=requirement.required_attachments,
            )
        )
    return {
        node_id: tuple(node_requirements)
        for node_id, node_requirements in grouped.items()
    }


def load_v1_graph_content(content: GraphContentModel) -> LoadedGraphContent:
    """Load the current frozen v1 graph-content input into solver-ready data."""

    if not isinstance(content, GraphContentModel):
        raise TypeError("content must be GraphContentModel")

    node_ids = {node.node_id for node in content.nodes}
    for requirement in content.route_requirements:
        if requirement.source_node_id not in node_ids:
            raise ValueError(
                f"Unknown source node id {requirement.source_node_id!r} in route requirements"
            )
        if requirement.sink_node_id not in node_ids:
            raise ValueError(
                f"Unknown sink node id {requirement.sink_node_id!r} in route requirements"
            )
    for requirement in content.screening_port_requirements:
        if requirement.node_id not in node_ids:
            raise ValueError(
                f"Unknown node id {requirement.node_id!r} in screening port requirements"
            )
    for group in content.ordered_same_row_groups:
        for node_id in group.ordered_node_ids:
            if node_id not in node_ids:
                raise ValueError(
                    f"Unknown node id {node_id!r} in ordered same-row groups"
                )

    loaded_definitions = load_v1_production_definitions(_node_kind_lookup(content))
    return LoadedGraphContent(
        node_definitions=loaded_definitions.node_definitions,
        visual_profile_catalog=loaded_definitions.visual_profile_catalog,
        node_metadata=tuple(_node_metadata(node) for node in content.nodes),
        ordered_same_row_groups=tuple(
            _same_row_group(group)
            for group in content.ordered_same_row_groups
        ),
        route_requirements=tuple(
            _route_requirement(requirement)
            for requirement in content.route_requirements
        ),
        schema_view=_build_schema_view(content.route_requirements),
        port_requirements_by_node_id=_build_port_requirements_by_node_id(
            content.screening_port_requirements
        ),
        routing_policy=content.routing_policy,
    )
