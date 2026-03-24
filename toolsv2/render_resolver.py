"""Concrete render resolver from committed runtime truth to resolved specs.

This module implements only the first render-preparation layer:
- consume committed runtime source-of-truth state
- resolve object anchors and port pixel positions
- resolve local built connections inside rendered owners
- resolve v1 external straight spans

It intentionally does not expand resolved specs into generic draw instructions
or perform final compositing/export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from toolsv2.render_contracts import (
    RenderResolver,
    ResolvedLocalConnectionSpec,
    ResolvedObjectRenderSpec,
    ResolvedPortRenderSpec,
    ResolvedSpanSpec,
)
from toolsv2.solver_common import Junction, ObjectRef, PortEdgeId, PortId, PortRef, RenderProfileKey
from toolsv2.solver_runtime import (
    Port,
    PortEdge,
    PortGraphState,
    RuntimeJunction,
    RuntimeNode,
)
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    ConnectionFamilyKey,
    DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY,
    LogicalToRenderMapper,
    PortGeometrySpec,
    VisualProfileCatalog,
)


ExternalConnectionFamilyResolver = Callable[[PortEdge], ConnectionFamilyKey]
_EDGE_PROFILE_NAMESPACE = "edge_family/"


def _object_ref_sort_key(object_ref: ObjectRef) -> tuple[str, str]:
    if isinstance(object_ref, Junction):
        return ("junction", f"{object_ref.x_rail_id}|{object_ref.y_rail_id}")
    return ("node", str(object_ref))


def _port_ref_sort_key(port_ref: PortRef) -> tuple[tuple[str, str], str]:
    return (_object_ref_sort_key(port_ref.owner_ref), str(port_ref.owner_local_key))


def _default_external_connection_family_resolver(edge: PortEdge) -> ConnectionFamilyKey:
    del edge
    return DEFAULT_EXTERNAL_STRAIGHT_CONNECTION_FAMILY_KEY


def _port_geometry_id(runtime_port: Port) -> PortId:
    return runtime_port.definition_port_id or runtime_port.port_ref.owner_local_key


def _require_profile_key(object_ref: ObjectRef, profile_key: RenderProfileKey | None) -> RenderProfileKey:
    if profile_key is None:
        raise ValueError(f"Renderable object {object_ref!r} requires a render-profile key")
    return profile_key


def _require_supported_anchor_offset(
    object_ref: ObjectRef,
    build_profile: BuildGeometryProfile,
) -> None:
    if build_profile.footprint.anchor_x != 0 or build_profile.footprint.anchor_y != 0:
        raise NotImplementedError(
            f"Non-zero LocalFootprint anchor offsets are not yet frozen for render resolution: {object_ref!r}"
        )


def _anchor_for_object(
    object_ref: ObjectRef,
    mapper: LogicalToRenderMapper,
    build_profile: BuildGeometryProfile,
) -> tuple[int, int]:
    _require_supported_anchor_offset(object_ref, build_profile)
    if not isinstance(object_ref, Junction):
        raise TypeError("Object anchors are resolved through occupied junction locations only")
    return mapper.x_pixel_for(object_ref.x_rail_id), mapper.y_pixel_for(object_ref.y_rail_id)


def _port_geometry_lookup(build_profile: BuildGeometryProfile) -> dict[PortId, PortGeometrySpec]:
    return {port.port_id: port for port in build_profile.ports}


def _resolve_port_specs(
    ports: tuple[Port, ...],
    anchor_x: int,
    anchor_y: int,
    build_profile: BuildGeometryProfile,
) -> tuple[ResolvedPortRenderSpec, ...]:
    geometry_by_port_id = _port_geometry_lookup(build_profile)
    resolved_ports: list[ResolvedPortRenderSpec] = []
    for runtime_port in sorted(ports, key=lambda port: str(port.port_ref.owner_local_key)):
        port_geometry_id = _port_geometry_id(runtime_port)
        port_geometry = geometry_by_port_id.get(port_geometry_id)
        if port_geometry is None:
            raise ValueError(
                f"Missing port geometry for port {runtime_port.port_ref!r} in profile {build_profile.profile_key!r}"
            )
        resolved_ports.append(
            ResolvedPortRenderSpec(
                port_id=runtime_port.port_ref.owner_local_key,
                pixel_x=anchor_x + port_geometry.offset_x,
                pixel_y=anchor_y + port_geometry.offset_y,
                attach_direction=port_geometry.attach_direction,
                attributes=runtime_port.attributes,
            )
        )
    return tuple(resolved_ports)


def _connection_family_for_internal_edge(
    edge: PortEdge,
    build_profile: BuildGeometryProfile,
    runtime_port_lookup: dict[PortRef, Port],
) -> ConnectionFamilyKey:
    runtime_port_a = runtime_port_lookup.get(edge.port_ref_a)
    runtime_port_b = runtime_port_lookup.get(edge.port_ref_b)
    if runtime_port_a is None or runtime_port_b is None:
        raise ValueError(f"Internal edge {edge.edge_id!r} references unknown port(s)")

    from_port_id = _port_geometry_id(runtime_port_a)
    to_port_id = _port_geometry_id(runtime_port_b)

    for transition in build_profile.internal_transitions:
        if transition.from_port_id == from_port_id and transition.to_port_id == to_port_id:
            return transition.connection_family_key
    for transition in build_profile.internal_transitions:
        if transition.from_port_id == to_port_id and transition.to_port_id == from_port_id:
            return transition.connection_family_key
    raise ValueError(
        f"Missing internal transition for built edge {edge.edge_id!r} between {from_port_id!r} and {to_port_id!r}"
    )


def _resolve_local_connections(
    owner_ref: ObjectRef,
    build_profile: BuildGeometryProfile,
    active_internal_edges_by_owner: dict[ObjectRef, tuple[PortEdge, ...]],
    runtime_port_lookup: dict[PortRef, Port],
) -> tuple[ResolvedLocalConnectionSpec, ...]:
    resolved_connections: list[ResolvedLocalConnectionSpec] = []
    for edge in active_internal_edges_by_owner.get(owner_ref, ()):
        resolved_connections.append(
            ResolvedLocalConnectionSpec(
                from_port_id=edge.port_ref_a.owner_local_key,
                to_port_id=edge.port_ref_b.owner_local_key,
                connection_family_key=_connection_family_for_internal_edge(
                    edge,
                    build_profile,
                    runtime_port_lookup,
                ),
                attributes=edge.attributes,
            )
        )
    return tuple(resolved_connections)


def _object_lookup(
    state: PortGraphState,
) -> dict[ObjectRef, RuntimeNode | RuntimeJunction]:
    lookup: dict[ObjectRef, RuntimeNode | RuntimeJunction] = {}
    for node in state.objects.nodes:
        lookup[node.node_id] = node
    for junction in state.objects.junctions:
        lookup[junction.junction_id] = junction
    return lookup


def _runtime_port_lookup(state: PortGraphState) -> dict[PortRef, Port]:
    return {
        port.port_ref: port
        for owner in (*state.objects.nodes, *state.objects.junctions)
        for port in owner.ports
    }


def _active_internal_edges_by_owner(state: PortGraphState) -> dict[ObjectRef, tuple[PortEdge, ...]]:
    grouped: dict[ObjectRef, list[PortEdge]] = {}
    for edge in sorted(state.objects.edges, key=lambda current_edge: str(current_edge.edge_id)):
        if not edge.is_active or edge.scope != "internal":
            continue
        if edge.owner_object_ref is None:
            raise ValueError(f"Internal edge {edge.edge_id!r} requires owner_object_ref")
        grouped.setdefault(edge.owner_object_ref, []).append(edge)
    return {owner_ref: tuple(edges) for owner_ref, edges in grouped.items()}


def _active_external_edges(state: PortGraphState) -> tuple[PortEdge, ...]:
    return tuple(
        edge
        for edge in sorted(state.objects.edges, key=lambda current_edge: str(current_edge.edge_id))
        if edge.is_active and edge.scope == "external"
    )


def _resolved_port_position_lookup(
    resolved_specs: tuple[ResolvedObjectRenderSpec, ...],
) -> dict[tuple[ObjectRef, PortId], ResolvedPortRenderSpec]:
    lookup: dict[tuple[ObjectRef, PortId], ResolvedPortRenderSpec] = {}
    for resolved_spec in resolved_specs:
        if isinstance(resolved_spec.instance_ref, str):
            owner_ref = resolved_spec.instance_ref
        elif isinstance(resolved_spec.instance_ref, Junction):
            owner_ref = resolved_spec.instance_ref
        else:
            continue
        for port in resolved_spec.ports:
            lookup[(owner_ref, port.port_id)] = port
    return lookup


def _edge_profile_key_for_family(family_key: ConnectionFamilyKey) -> RenderProfileKey:
    return RenderProfileKey(f"{_EDGE_PROFILE_NAMESPACE}{family_key}")


def _resolve_external_span(
    edge: PortEdge,
    resolved_port_lookup: dict[tuple[ObjectRef, PortId], ResolvedPortRenderSpec],
    connection_family_key: ConnectionFamilyKey,
    visual_profile_catalog: VisualProfileCatalog,
) -> ResolvedSpanSpec:
    family_profile = visual_profile_catalog.connection_family_profile(connection_family_key)
    if family_profile.rule_kind != "repeat_span":
        raise ValueError(
            f"External edge {edge.edge_id!r} requires repeat-span family, got {family_profile.rule_kind!r}"
        )
    if family_profile.shape_kind != "axis_aligned_straight":
        raise ValueError(
            f"External edge {edge.edge_id!r} requires axis-aligned straight family, got {family_profile.shape_kind!r}"
        )

    port_a = resolved_port_lookup.get((edge.port_ref_a.owner_ref, edge.port_ref_a.owner_local_key))
    port_b = resolved_port_lookup.get((edge.port_ref_b.owner_ref, edge.port_ref_b.owner_local_key))
    if port_a is None or port_b is None:
        raise ValueError(f"External edge {edge.edge_id!r} requires resolved endpoint port positions")
    if port_a.pixel_x != port_b.pixel_x and port_a.pixel_y != port_b.pixel_y:
        raise ValueError(f"External edge {edge.edge_id!r} is not axis aligned in render space")

    return ResolvedSpanSpec(
        connection_family_key=connection_family_key,
        start_x=port_a.pixel_x,
        start_y=port_a.pixel_y,
        end_x=port_b.pixel_x,
        end_y=port_b.pixel_y,
        attributes=edge.attributes,
    )


@dataclass(frozen=True, slots=True)
class V1RenderResolver:
    """Resolve committed runtime truth into render-ready object specs."""

    resolve_external_connection_family: ExternalConnectionFamilyResolver = field(
        default=_default_external_connection_family_resolver
    )

    def __call__(
        self,
        state: PortGraphState,
        mapper: LogicalToRenderMapper,
        visual_profile_catalog: VisualProfileCatalog,
    ) -> tuple[ResolvedObjectRenderSpec, ...]:
        if not isinstance(state, PortGraphState):
            raise TypeError("state must be PortGraphState")

        object_lookup = _object_lookup(state)
        runtime_port_lookup = _runtime_port_lookup(state)
        active_internal_edges_by_owner = _active_internal_edges_by_owner(state)

        resolved_objects: list[ResolvedObjectRenderSpec] = []

        for node in sorted(state.objects.nodes, key=lambda current_node: str(current_node.node_id)):
            if not node.is_active:
                continue
            if node.current_junction_id is None:
                raise ValueError(f"Active runtime node {node.node_id!r} requires current_junction_id")
            profile_key = _require_profile_key(node.node_id, node.render_profile.profile_key)
            build_profile = visual_profile_catalog.build_geometry_profile(profile_key)
            visual_profile_catalog.render_style_profile(profile_key)
            anchor_x, anchor_y = _anchor_for_object(node.current_junction_id, mapper, build_profile)
            resolved_objects.append(
                ResolvedObjectRenderSpec(
                    instance_ref=node.node_id,
                    profile_key=profile_key,
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                    ports=_resolve_port_specs(node.ports, anchor_x, anchor_y, build_profile),
                    local_connections=_resolve_local_connections(
                        node.node_id,
                        build_profile,
                        active_internal_edges_by_owner,
                        runtime_port_lookup,
                    ),
                    attributes=node.attributes,
                )
            )

        for junction in sorted(
            state.objects.junctions,
            key=lambda current_junction: _object_ref_sort_key(current_junction.junction_id),
        ):
            if not junction.is_active:
                if active_internal_edges_by_owner.get(junction.junction_id):
                    raise ValueError(
                        f"Occupied junction {junction.junction_id!r} must not own active local connection edges"
                    )
                continue
            profile_key = _require_profile_key(junction.junction_id, junction.render_profile.profile_key)
            build_profile = visual_profile_catalog.build_geometry_profile(profile_key)
            visual_profile_catalog.render_style_profile(profile_key)
            local_connections = _resolve_local_connections(
                junction.junction_id,
                build_profile,
                active_internal_edges_by_owner,
                runtime_port_lookup,
            )
            if not local_connections:
                continue
            anchor_x, anchor_y = _anchor_for_object(junction.junction_id, mapper, build_profile)
            resolved_objects.append(
                ResolvedObjectRenderSpec(
                    instance_ref=junction.junction_id,
                    profile_key=profile_key,
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                    ports=_resolve_port_specs(junction.ports, anchor_x, anchor_y, build_profile),
                    local_connections=local_connections,
                    attributes=junction.attributes,
                )
            )

        resolved_specs = tuple(resolved_objects)
        resolved_port_lookup = _resolved_port_position_lookup(resolved_specs)
        for edge in _active_external_edges(state):
            endpoint_object_a = object_lookup.get(edge.port_ref_a.owner_ref)
            endpoint_object_b = object_lookup.get(edge.port_ref_b.owner_ref)
            if endpoint_object_a is None or endpoint_object_b is None:
                raise ValueError(f"External edge {edge.edge_id!r} references unknown endpoint owner(s)")
            if not endpoint_object_a.is_active or not endpoint_object_b.is_active:
                continue

            connection_family_key = self.resolve_external_connection_family(edge)
            span = _resolve_external_span(
                edge,
                resolved_port_lookup,
                connection_family_key,
                visual_profile_catalog,
            )
            resolved_objects.append(
                ResolvedObjectRenderSpec(
                    instance_ref=edge.edge_id,
                    profile_key=_edge_profile_key_for_family(connection_family_key),
                    anchor_x=span.start_x,
                    anchor_y=span.start_y,
                    spans=(span,),
                    attributes=edge.attributes,
                )
            )

        return tuple(resolved_objects)


def build_v1_render_resolver() -> RenderResolver:
    """Return the first concrete committed-runtime render resolver."""

    return V1RenderResolver()
