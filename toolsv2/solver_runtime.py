"""Runtime object layer for the solver.

These types describe instantiated logical objects and graph/reference state.
They must not embed routing algorithms, occupancy masking semantics, or path
objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from toolsv2.solver_common import (
    ActiveGridState,
    Attributes,
    EdgeScope,
    EdgeTraversalMode,
    Junction,
    NodeId,
    ObjectRef,
    PortEdgeId,
    PortId,
    PortRef,
    _ensure_unique_hashables,
    _ensure_unique_keys,
    _ensure_unique_strings,
)
from toolsv2.solver_schema import RenderProfileRef
from toolsv2.visual_profiles import DEFAULT_PLAIN_JUNCTION_PROFILE_KEY


@dataclass(frozen=True, slots=True)
class Port:
    """A concrete port owned by a node or a junction.

    ``definition_port_id`` is the schema-level port id when one is known.
    Junction-owned port schema details remain open and therefore may omit it.
    """

    port_ref: PortRef
    definition_port_id: PortId | None = None
    is_active: bool = True
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.definition_port_id is None and isinstance(self.port_ref.owner_ref, str):
            object.__setattr__(self, "definition_port_id", self.port_ref.owner_local_key)
        if not isinstance(self.is_active, bool):
            raise TypeError("Port.is_active must be bool")
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("Port.render_profile must be RenderProfileRef")
        _ensure_unique_keys("Port.attributes", self.attributes)


Endpoint = Port


_DEFAULT_JUNCTION_PORT_LOCAL_KEYS: tuple[PortId, ...] = (
    PortId("north"),
    PortId("south"),
    PortId("west"),
    PortId("east"),
)


@dataclass(frozen=True, slots=True)
class RuntimeNode:
    """Runtime logical node state with owned ports."""

    node_id: NodeId
    schema_node_id: NodeId | None = None
    current_junction_id: Junction | None = None
    is_active: bool = True
    ports: tuple[Port, ...] = ()
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.schema_node_id is None:
            object.__setattr__(self, "schema_node_id", self.node_id)
        if not isinstance(self.is_active, bool):
            raise TypeError("RuntimeNode.is_active must be bool")
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("RuntimeNode.render_profile must be RenderProfileRef")
        for port in self.ports:
            if port.port_ref.owner_ref != self.node_id:
                raise ValueError("RuntimeNode.ports must be owned by the runtime node")
        _ensure_unique_strings(
            "RuntimeNode.ports",
            tuple(str(port.port_ref.owner_local_key) for port in self.ports),
        )
        _ensure_unique_keys("RuntimeNode.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class RuntimeJunction:
    """Runtime logical junction state with owned ports."""

    junction_id: Junction
    schema_junction_id: Junction | None = None
    occupying_node_id: NodeId | None = None
    is_active: bool = True
    ports: tuple[Port, ...] = ()
    render_profile: RenderProfileRef = field(default_factory=RenderProfileRef)
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.schema_junction_id is None:
            object.__setattr__(self, "schema_junction_id", self.junction_id)
        if not isinstance(self.is_active, bool):
            raise TypeError("RuntimeJunction.is_active must be bool")
        if not isinstance(self.render_profile, RenderProfileRef):
            raise TypeError("RuntimeJunction.render_profile must be RenderProfileRef")
        for port in self.ports:
            if port.port_ref.owner_ref != self.junction_id:
                raise ValueError("RuntimeJunction.ports must be owned by the runtime junction")
        _ensure_unique_strings(
            "RuntimeJunction.ports",
            tuple(str(port.port_ref.owner_local_key) for port in self.ports),
        )
        _ensure_unique_keys("RuntimeJunction.attributes", self.attributes)


def _build_default_junction_ports(junction_id: Junction) -> tuple[Port, ...]:
    """Return the minimal default interface ports for one runtime junction.

    These owner-scoped directional keys are the stable default junction-port
    substrate only. Richer junction-port schema, routing semantics, masking,
    and rendering remain open.
    """

    return tuple(
        Port(
            port_ref=PortRef(
                owner_ref=junction_id,
                owner_local_key=local_key,
            ),
        )
        for local_key in _DEFAULT_JUNCTION_PORT_LOCAL_KEYS
    )


def build_runtime_junctions_for_active_grid(
    active_grid: ActiveGridState,
) -> tuple[RuntimeJunction, ...]:
    """Instantiate runtime junction objects for every active-grid intersection.

    This eagerly materializes runtime junction containers from the current
    logical grid only. It does not infer occupancy, built edges, or any
    routing/path semantics. The default plain-junction render-profile key is
    attached only as build/render metadata for downstream consumers.
    """

    if not isinstance(active_grid, ActiveGridState):
        raise TypeError("active_grid must be ActiveGridState")

    ordered_x_rails = tuple(sorted(active_grid.x_rails, key=lambda rail: rail.order))
    ordered_y_rails = tuple(sorted(active_grid.y_rails, key=lambda rail: rail.logical_rank))

    return tuple(
        RuntimeJunction(
            junction_id=Junction(
                x_rail_id=x_rail.rail_id,
                y_rail_id=y_rail.rail_id,
            ),
            ports=_build_default_junction_ports(
                Junction(
                    x_rail_id=x_rail.rail_id,
                    y_rail_id=y_rail.rail_id,
                )
            ),
            render_profile=RenderProfileRef(
                profile_key=DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
            ),
        )
        for x_rail in ordered_x_rails
        for y_rail in ordered_y_rails
    )


@dataclass(frozen=True, slots=True)
class PortEdge:
    """A first-class built edge between two ports.

    Endpoint ordering is stored only as neutral labels. Scope is provenance
    only. Path logic may use edge identity and endpoint transitions, but must
    not depend on edge type, render style, or route-commit semantics.
    """

    edge_id: PortEdgeId
    port_ref_a: PortRef
    port_ref_b: PortRef
    scope: EdgeScope
    traversal_mode: EdgeTraversalMode = "bidirectional"
    owner_object_ref: ObjectRef | None = None
    is_active: bool = True
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        if self.port_ref_a == self.port_ref_b:
            raise ValueError("PortEdge endpoints must be distinct port references")
        if self.scope not in ("internal", "external"):
            raise ValueError("PortEdge.scope must be 'internal' or 'external'")
        if self.traversal_mode not in ("bidirectional", "a_to_b", "b_to_a"):
            raise ValueError(
                "PortEdge.traversal_mode must be 'bidirectional', 'a_to_b', or 'b_to_a'"
            )
        if self.scope == "internal":
            if self.owner_object_ref is None:
                raise ValueError("Internal PortEdge requires owner_object_ref")
            if self.port_ref_a.owner_ref != self.owner_object_ref:
                raise ValueError("Internal PortEdge port_ref_a must belong to owner_object_ref")
            if self.port_ref_b.owner_ref != self.owner_object_ref:
                raise ValueError("Internal PortEdge port_ref_b must belong to owner_object_ref")
        else:
            if self.owner_object_ref is not None:
                raise ValueError("External PortEdge must not declare owner_object_ref")
        if not isinstance(self.is_active, bool):
            raise TypeError("PortEdge.is_active must be bool")
        _ensure_unique_keys("PortEdge.attributes", self.attributes)


def _collect_ports(
    nodes: tuple[RuntimeNode, ...],
    junctions: tuple[RuntimeJunction, ...],
) -> tuple[Port, ...]:
    return tuple(
        port
        for owner in (*nodes, *junctions)
        for port in owner.ports
    )


def _port_lookup(objects: "RuntimeObjectSet") -> dict[PortRef, Port]:
    return {port.port_ref: port for port in _collect_ports(objects.nodes, objects.junctions)}


def _edge_lookup(objects: "RuntimeObjectSet") -> dict[PortEdgeId, PortEdge]:
    return {edge.edge_id: edge for edge in objects.edges}


def is_object_ref_active(objects: "RuntimeObjectSet", object_ref: ObjectRef) -> bool:
    """Return whether a runtime object is currently active in source-of-truth state."""

    if isinstance(object_ref, Junction):
        for junction in objects.junctions:
            if junction.junction_id == object_ref:
                return junction.is_active
        raise KeyError(f"Unknown junction object_ref: {object_ref}")

    for node in objects.nodes:
        if node.node_id == object_ref:
            return node.is_active
    raise KeyError(f"Unknown node object_ref: {object_ref}")


def is_port_ref_usable(objects: "RuntimeObjectSet", port_ref: PortRef) -> bool:
    """Return whether a port is currently usable in source-of-truth state."""

    port = _port_lookup(objects).get(port_ref)
    if port is None:
        raise KeyError(f"Unknown port_ref: {port_ref}")
    return port.is_active and is_object_ref_active(objects, port_ref.owner_ref)


def is_edge_id_usable(objects: "RuntimeObjectSet", edge_id: PortEdgeId) -> bool:
    """Return whether an edge is currently usable in source-of-truth state."""

    edge = _edge_lookup(objects).get(edge_id)
    if edge is None:
        raise KeyError(f"Unknown edge_id: {edge_id}")
    return (
        edge.is_active
        and is_port_ref_usable(objects, edge.port_ref_a)
        and is_port_ref_usable(objects, edge.port_ref_b)
    )


@dataclass(frozen=True, slots=True)
class RuntimeObjectSet:
    """Built logical objects, separate from the graph index."""

    nodes: tuple[RuntimeNode, ...] = ()
    junctions: tuple[RuntimeJunction, ...] = ()
    edges: tuple[PortEdge, ...] = ()

    def __post_init__(self) -> None:
        node_ids = tuple(node.node_id for node in self.nodes)
        junction_ids = tuple(junction.junction_id for junction in self.junctions)
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        ports = _collect_ports(self.nodes, self.junctions)
        port_refs = tuple(port.port_ref for port in ports)

        _ensure_unique_hashables("RuntimeObjectSet.nodes", node_ids)
        _ensure_unique_hashables("RuntimeObjectSet.junctions", junction_ids)
        _ensure_unique_hashables("RuntimeObjectSet.edges", edge_ids)
        _ensure_unique_hashables("RuntimeObjectSet.ports", port_refs)

        node_id_set = set(node_ids)
        junction_id_set = set(junction_ids)
        port_ref_set = set(port_refs)
        junction_lookup = {junction.junction_id: junction for junction in self.junctions}
        node_lookup = {node.node_id: node for node in self.nodes}

        for edge in self.edges:
            if edge.port_ref_a not in port_ref_set:
                raise ValueError("RuntimeObjectSet edge port_ref_a must reference an existing port")
            if edge.port_ref_b not in port_ref_set:
                raise ValueError("RuntimeObjectSet edge port_ref_b must reference an existing port")

        for node in self.nodes:
            if node.schema_node_id is None:
                raise ValueError("RuntimeNode.schema_node_id must not be None after initialization")
            if node.current_junction_id is None:
                continue
            if node.current_junction_id not in junction_id_set:
                raise ValueError("RuntimeNode.current_junction_id must reference an existing runtime junction")
            occupying_node_id = junction_lookup[node.current_junction_id].occupying_node_id
            if occupying_node_id is not None and occupying_node_id != node.node_id:
                raise ValueError("Occupied node and junction lookup must agree when both are present")
            if occupying_node_id == node.node_id and junction_lookup[node.current_junction_id].is_active:
                raise ValueError("A runtime junction occupied by a node must be inactive")

        for junction in self.junctions:
            if junction.schema_junction_id is None:
                raise ValueError("RuntimeJunction.schema_junction_id must not be None after initialization")
            if junction.occupying_node_id is None:
                continue
            if junction.is_active:
                raise ValueError("A runtime junction occupied by a node must be inactive")
            if junction.occupying_node_id not in node_id_set:
                raise ValueError("RuntimeJunction.occupying_node_id must reference an existing runtime node")
            current_junction_id = node_lookup[junction.occupying_node_id].current_junction_id
            if current_junction_id is not None and current_junction_id != junction.junction_id:
                raise ValueError("Occupied node and junction lookup must agree when both are present")


@dataclass(frozen=True, slots=True)
class PortGraphIndex:
    """Logical graph/index data over references to built objects."""

    port_refs: tuple[PortRef, ...] = ()
    edge_ids: tuple[PortEdgeId, ...] = ()
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        _ensure_unique_hashables("PortGraphIndex.port_refs", self.port_refs)
        _ensure_unique_hashables("PortGraphIndex.edge_ids", self.edge_ids)
        _ensure_unique_keys("PortGraphIndex.attributes", self.attributes)


@dataclass(frozen=True, slots=True)
class PortGraphState:
    """Aggregate runtime object set plus a separate graph/index view."""

    objects: RuntimeObjectSet = field(default_factory=RuntimeObjectSet)
    graph: PortGraphIndex = field(default_factory=PortGraphIndex)

    def __post_init__(self) -> None:
        if not isinstance(self.objects, RuntimeObjectSet):
            raise TypeError("PortGraphState.objects must be RuntimeObjectSet")
        if not isinstance(self.graph, PortGraphIndex):
            raise TypeError("PortGraphState.graph must be PortGraphIndex")

        object_port_refs = {
            port.port_ref
            for port in _collect_ports(self.objects.nodes, self.objects.junctions)
        }
        object_edge_ids = {edge.edge_id for edge in self.objects.edges}

        for port_ref in self.graph.port_refs:
            if port_ref not in object_port_refs:
                raise ValueError("PortGraphIndex.port_refs must resolve to built port objects")

        for edge_id in self.graph.edge_ids:
            if edge_id not in object_edge_ids:
                raise ValueError("PortGraphIndex.edge_ids must resolve to built edge objects")
