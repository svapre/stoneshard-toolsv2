"""Production bridge from one placement seed to one initial runtime snapshot.

This module materializes the initial routing runtime state for a fixed active
grid and fixed node-definition map. It does not search, route, commit, refine,
or mutate shared state in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from toolsv2.placement_solver import PlacementSeed
from toolsv2.solver_common import ActiveGridState, Junction, NodeId, PortRef
from toolsv2.solver_runtime import (
    Port,
    PortGraphIndex,
    PortGraphState,
    RuntimeJunction,
    RuntimeNode,
    RuntimeObjectSet,
    build_runtime_junctions_for_active_grid,
)
from toolsv2.solver_schema import NodeDefinition, PortDefinition


def _build_runtime_port_for_node(
    node_id: NodeId,
    port_definition: PortDefinition,
) -> Port:
    return Port(
        port_ref=PortRef(
            owner_ref=node_id,
            owner_local_key=port_definition.port_id,
        ),
        definition_port_id=port_definition.port_id,
        render_profile=port_definition.render_profile,
        attributes=port_definition.attributes,
    )


def _build_runtime_node_for_assignment(
    node_definition: NodeDefinition,
    occupied_junction: Junction,
) -> RuntimeNode:
    return RuntimeNode(
        node_id=node_definition.node_id,
        schema_node_id=node_definition.node_id,
        current_junction_id=occupied_junction,
        is_active=True,
        ports=tuple(
            _build_runtime_port_for_node(node_definition.node_id, port_definition)
            for port_definition in node_definition.ports
        ),
        render_profile=node_definition.render_profile,
        attributes=node_definition.attributes,
    )


def _occupied_junction_lookup(placement_seed: PlacementSeed) -> dict[Junction, NodeId]:
    occupied: dict[Junction, NodeId] = {}
    for node_id, junction in placement_seed.assignments.items():
        if junction in occupied:
            raise ValueError("PlacementSeed assigns multiple nodes to the same junction")
        occupied[junction] = node_id
    return occupied


def _apply_junction_occupancy(
    runtime_junctions: tuple[RuntimeJunction, ...],
    occupied_junctions: Mapping[Junction, NodeId],
) -> tuple[RuntimeJunction, ...]:
    return tuple(
        RuntimeJunction(
            junction_id=runtime_junction.junction_id,
            schema_junction_id=runtime_junction.schema_junction_id,
            occupying_node_id=occupied_junctions.get(runtime_junction.junction_id),
            is_active=runtime_junction.junction_id not in occupied_junctions,
            ports=runtime_junction.ports,
            render_profile=runtime_junction.render_profile,
            attributes=runtime_junction.attributes,
        )
        for runtime_junction in runtime_junctions
    )


def _port_refs_for_objects(
    runtime_nodes: tuple[RuntimeNode, ...],
    runtime_junctions: tuple[RuntimeJunction, ...],
) -> tuple[PortRef, ...]:
    return tuple(
        port.port_ref
        for owner in (*runtime_nodes, *runtime_junctions)
        for port in owner.ports
    )


@dataclass(frozen=True, slots=True)
class V1RuntimeSnapshotBuilder:
    """Pure deterministic bridge from one placement seed to one runtime snapshot."""

    active_grid: ActiveGridState
    node_definitions: Mapping[NodeId, NodeDefinition]

    def __call__(self, placement_seed: PlacementSeed) -> PortGraphState:
        if not isinstance(placement_seed, PlacementSeed):
            raise TypeError("placement_seed must be PlacementSeed")

        occupied_junctions = _occupied_junction_lookup(placement_seed)
        all_runtime_junctions = build_runtime_junctions_for_active_grid(self.active_grid)
        junction_id_set = {runtime_junction.junction_id for runtime_junction in all_runtime_junctions}

        for assigned_junction in occupied_junctions:
            if assigned_junction not in junction_id_set:
                raise ValueError("PlacementSeed assignment must reference a junction on the active grid")

        runtime_nodes: list[RuntimeNode] = []
        for node_id in sorted(placement_seed.assignments, key=str):
            node_definition = self.node_definitions.get(node_id)
            if node_definition is None:
                raise ValueError(f"Missing NodeDefinition for node {node_id!r}")
            runtime_nodes.append(
                _build_runtime_node_for_assignment(
                    node_definition=node_definition,
                    occupied_junction=placement_seed.assignments[node_id],
                )
            )

        runtime_junctions = _apply_junction_occupancy(
            all_runtime_junctions,
            occupied_junctions,
        )

        runtime_objects = RuntimeObjectSet(
            nodes=tuple(runtime_nodes),
            junctions=runtime_junctions,
            edges=(),
        )
        return PortGraphState(
            objects=runtime_objects,
            graph=PortGraphIndex(
                port_refs=_port_refs_for_objects(runtime_objects.nodes, runtime_objects.junctions),
                edge_ids=(),
            ),
        )


def build_v1_runtime_snapshot_builder(
    active_grid: ActiveGridState,
    node_definitions: Mapping[NodeId, NodeDefinition],
) -> V1RuntimeSnapshotBuilder:
    """Bind the fixed active grid and node definitions into the production builder."""

    return V1RuntimeSnapshotBuilder(
        active_grid=active_grid,
        node_definitions=dict(node_definitions),
    )
