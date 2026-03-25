"""Build generic glow sections from one successful solved requirement tree."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from toolsv2.glow.contracts import GlowDependencyGroups, GlowPointSpec
from toolsv2.graph_content import GraphContentRouteRequirement
from toolsv2.production_family_catalog import V1_AND_KNOT_KIND
from toolsv2.render_export import render_v1_successful_solve_result
from toolsv2.render_layout_profiles import RenderLayoutProfile
from toolsv2.run_branch import SkillTreeRunResult
from toolsv2.solver_common import Junction, NodeId, PortRef


ActivationGroup = tuple[str, ...]
ArcKey = tuple[PortRef, PortRef]


def _object_ref_sort_key(object_ref) -> tuple[str, str]:
    if isinstance(object_ref, Junction):
        return ("junction", f"{object_ref.x_rail_id}|{object_ref.y_rail_id}")
    return ("node", str(object_ref))


def _port_ref_sort_key(port_ref: PortRef) -> tuple[tuple[str, str], str]:
    return (_object_ref_sort_key(port_ref.owner_ref), str(port_ref.owner_local_key))


def _arc_sort_key(arc_key: ArcKey) -> tuple[tuple[tuple[str, str], str], tuple[tuple[str, str], str]]:
    return (_port_ref_sort_key(arc_key[0]), _port_ref_sort_key(arc_key[1]))


def _activation_group_sort_key(group: ActivationGroup) -> tuple[int, tuple[str, ...]]:
    return (len(group), group)


@dataclass(frozen=True, slots=True)
class GlowSection:
    """One geometric glow section before sprite rasterization."""

    section_id: str
    arc_keys: frozenset[ArcKey]
    activation_groups: GlowDependencyGroups
    line_dependency_groups: GlowDependencyGroups
    sink_point_ids: tuple[str, ...]
    draw_knot: bool
    root_port_refs: tuple[PortRef, ...]
    leaf_port_refs: tuple[PortRef, ...]


@dataclass(frozen=True, slots=True)
class GlowSectionBuildResult:
    """Generic point specs plus unrasterized line sections."""

    point_specs: tuple[GlowPointSpec, ...]
    sections: tuple[GlowSection, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedPointPort:
    point_id: str
    anchor_x: int
    anchor_y: int
    port_pixels_by_port_id: Mapping[str, tuple[int, int]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "port_pixels_by_port_id",
            MappingProxyType(dict(self.port_pixels_by_port_id)),
        )


def _skills_by_id(run_result: SkillTreeRunResult):
    return {skill.skill_id: skill for skill in run_result.requirement_spec.skills}


def _compiled_route_requirements_by_id(
    run_result: SkillTreeRunResult,
) -> dict[str, GraphContentRouteRequirement]:
    return {
        requirement.requirement_id: requirement
        for requirement in run_result.compiled_content.graph_content.route_requirements
    }


def _node_kinds_by_node_id(run_result: SkillTreeRunResult) -> dict[NodeId, str]:
    return {
        node.node_id: node.kind
        for node in run_result.compiled_content.graph_content.nodes
    }


def _incoming_source_skill_ids_by_gate_id(
    run_result: SkillTreeRunResult,
) -> dict[NodeId, tuple[str, ...]]:
    skills_by_id = _skills_by_id(run_result)
    tier_slot_key = {
        skill.skill_id: (skill.tier, skill.slot, skill.skill_id)
        for skill in run_result.requirement_spec.skills
    }
    grouped: dict[NodeId, set[str]] = defaultdict(set)
    node_kinds = _node_kinds_by_node_id(run_result)
    for requirement in run_result.compiled_content.graph_content.route_requirements:
        sink_node_id = requirement.sink_node_id
        if node_kinds.get(sink_node_id) != V1_AND_KNOT_KIND:
            continue
        source_id = str(requirement.source_node_id)
        if source_id not in skills_by_id:
            continue
        grouped[sink_node_id].add(source_id)
    return {
        gate_id: tuple(
            sorted(source_ids, key=lambda skill_id: tier_slot_key[skill_id])
        )
        for gate_id, source_ids in grouped.items()
    }


def _activation_group_for_source_object(
    run_result: SkillTreeRunResult,
    *,
    source_node_id: NodeId,
) -> ActivationGroup:
    node_kinds = _node_kinds_by_node_id(run_result)
    if node_kinds.get(source_node_id) == V1_AND_KNOT_KIND:
        gate_inputs = _incoming_source_skill_ids_by_gate_id(run_result).get(source_node_id)
        if not gate_inputs:
            raise ValueError(f"AND gate {source_node_id!r} is missing direct input skill ids")
        return tuple(gate_inputs)
    return (str(source_node_id),)


def _route_plan_arcs(route_plan) -> tuple[ArcKey, ...]:
    return tuple(
        (step.from_entry_context.current_port_ref, step.to_entry_context.current_port_ref)
        for step in route_plan.steps
    )


def _resolved_points_by_id(
    run_result: SkillTreeRunResult,
    *,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> dict[str, _ResolvedPointPort]:
    successful_result = run_result.solve_result.successful_current_grid_result
    if successful_result is None or successful_result.final_state is None:
        raise ValueError("Glow export requires a successful solved tree")
    render_result = render_v1_successful_solve_result(
        successful_result,
        render_layout_profile=render_layout_profile,
    )
    point_ids = {skill.skill_id for skill in run_result.requirement_spec.skills}
    resolved_points: dict[str, _ResolvedPointPort] = {}
    for resolved_object in render_result.resolved_objects:
        if not isinstance(resolved_object.instance_ref, str):
            continue
        point_id = str(resolved_object.instance_ref)
        if point_id not in point_ids:
            continue
        resolved_points[point_id] = _ResolvedPointPort(
            point_id=point_id,
            anchor_x=resolved_object.anchor_x,
            anchor_y=resolved_object.anchor_y,
            port_pixels_by_port_id={
                str(port.port_id): (port.pixel_x, port.pixel_y)
                for port in resolved_object.ports
            },
        )
    missing = point_ids.difference(resolved_points)
    if missing:
        raise ValueError(f"Glow export missing resolved point anchors for: {sorted(missing)!r}")
    return resolved_points


def _port_pixel_lookup_for_resolved_state(
    run_result: SkillTreeRunResult,
    *,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> dict[PortRef, tuple[int, int]]:
    successful_result = run_result.solve_result.successful_current_grid_result
    if successful_result is None or successful_result.final_state is None:
        raise ValueError("Glow export requires a successful solved tree")
    render_result = render_v1_successful_solve_result(
        successful_result,
        render_layout_profile=render_layout_profile,
    )
    lookup: dict[PortRef, tuple[int, int]] = {}
    for resolved_object in render_result.resolved_objects:
        instance_ref = resolved_object.instance_ref
        if isinstance(instance_ref, str) or isinstance(instance_ref, Junction):
            for port in resolved_object.ports:
                lookup[
                    PortRef(owner_ref=instance_ref, owner_local_key=port.port_id)
                ] = (port.pixel_x, port.pixel_y)
    return lookup


def _component_arc_sets_by_signature(
    arc_activation_groups: Mapping[ArcKey, frozenset[ActivationGroup]],
) -> tuple[tuple[frozenset[ActivationGroup], frozenset[ArcKey]], ...]:
    arcs_by_signature: dict[frozenset[ActivationGroup], set[ArcKey]] = defaultdict(set)
    for arc_key, activation_groups in arc_activation_groups.items():
        arcs_by_signature[activation_groups].add(arc_key)

    grouped_components: list[tuple[frozenset[ActivationGroup], frozenset[ArcKey]]] = []
    for signature in sorted(
        arcs_by_signature,
        key=lambda item: (
            len(item),
            tuple(sorted(item, key=_activation_group_sort_key)),
        ),
    ):
        arcs = arcs_by_signature[signature]
        arc_adjacency: dict[ArcKey, set[ArcKey]] = {arc: set() for arc in arcs}
        arcs_by_endpoint: dict[PortRef, set[ArcKey]] = defaultdict(set)
        for arc in arcs:
            arcs_by_endpoint[arc[0]].add(arc)
            arcs_by_endpoint[arc[1]].add(arc)
        for adjacent_arcs in arcs_by_endpoint.values():
            adjacent_arc_list = tuple(adjacent_arcs)
            for arc in adjacent_arc_list:
                arc_adjacency[arc].update(other_arc for other_arc in adjacent_arc_list if other_arc != arc)

        seen: set[ArcKey] = set()
        for arc in sorted(arcs, key=_arc_sort_key):
            if arc in seen:
                continue
            component: set[ArcKey] = set()
            queue = deque([arc])
            seen.add(arc)
            while queue:
                current = queue.popleft()
                component.add(current)
                for neighbor in sorted(arc_adjacency[current], key=_arc_sort_key):
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    queue.append(neighbor)
            grouped_components.append((signature, frozenset(component)))

    return tuple(grouped_components)


def _root_and_leaf_ports_for_component(
    component_arcs: frozenset[ArcKey],
) -> tuple[tuple[PortRef, ...], tuple[PortRef, ...]]:
    indegree: dict[PortRef, int] = defaultdict(int)
    outdegree: dict[PortRef, int] = defaultdict(int)
    nodes: set[PortRef] = set()
    for from_port_ref, to_port_ref in component_arcs:
        nodes.add(from_port_ref)
        nodes.add(to_port_ref)
        outdegree[from_port_ref] += 1
        indegree[to_port_ref] += 1
    root_ports = tuple(
        sorted(
            (port_ref for port_ref in nodes if indegree.get(port_ref, 0) == 0),
            key=_port_ref_sort_key,
        )
    )
    leaf_ports = tuple(
        sorted(
            (port_ref for port_ref in nodes if outdegree.get(port_ref, 0) == 0),
            key=_port_ref_sort_key,
        )
    )
    return root_ports, leaf_ports


def _topologically_sorted_activation_groups(
    activation_groups: frozenset[ActivationGroup],
) -> GlowDependencyGroups:
    return tuple(sorted(activation_groups, key=_activation_group_sort_key))


def _compress_component_sequence(component_ids: tuple[str, ...]) -> tuple[str, ...]:
    compressed: list[str] = []
    for component_id in component_ids:
        if compressed and compressed[-1] == component_id:
            continue
        compressed.append(component_id)
    return tuple(compressed)


def build_glow_sections_for_successful_run(
    run_result: SkillTreeRunResult,
    *,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> GlowSectionBuildResult:
    """Build generic glow point specs and unrasterized line sections for one run."""

    successful_result = run_result.solve_result.successful_current_grid_result
    if successful_result is None or successful_result.final_state is None:
        raise ValueError("Glow export requires a successful solved tree")
    placement_result = successful_result.placement_orchestration_result
    if placement_result is None or placement_result.route_orchestration_result is None:
        raise ValueError("Glow export requires completed route orchestration")

    resolved_points = _resolved_points_by_id(
        run_result,
        render_layout_profile=render_layout_profile,
    )
    route_requirements_by_id = _compiled_route_requirements_by_id(run_result)
    route_requirement_ids = {
        requirement.requirement_id
        for requirement in run_result.compiled_content.graph_content.route_requirements
    }

    arc_activation_groups: dict[ArcKey, set[ActivationGroup]] = defaultdict(set)
    source_node_ids_by_arc: dict[ArcKey, set[str]] = defaultdict(set)
    route_plan_arcs_by_requirement_id: dict[str, tuple[ArcKey, ...]] = {}
    activation_group_by_requirement_id: dict[str, ActivationGroup] = {}

    for completed in placement_result.route_orchestration_result.completed:
        requirement_id = completed.route_requirement_id
        if requirement_id not in route_requirement_ids:
            continue
        compiled_requirement = route_requirements_by_id[requirement_id]
        activation_group = _activation_group_for_source_object(
            run_result,
            source_node_id=compiled_requirement.source_node_id,
        )
        activation_group_by_requirement_id[requirement_id] = activation_group
        route_plan_arcs = _route_plan_arcs(completed.route_plan)
        route_plan_arcs_by_requirement_id[requirement_id] = route_plan_arcs
        for arc_key in route_plan_arcs:
            arc_activation_groups[arc_key].add(activation_group)
            source_node_ids_by_arc[arc_key].add(str(compiled_requirement.source_node_id))

    component_specs = _component_arc_sets_by_signature(
        {
            arc_key: frozenset(activation_groups)
            for arc_key, activation_groups in arc_activation_groups.items()
        }
    )

    component_id_by_arc: dict[ArcKey, str] = {}
    activation_groups_by_component_id: dict[str, GlowDependencyGroups] = {}
    source_node_ids_by_component_id: dict[str, set[str]] = defaultdict(set)
    root_ports_by_component_id: dict[str, tuple[PortRef, ...]] = {}
    leaf_ports_by_component_id: dict[str, tuple[PortRef, ...]] = {}
    component_arcs_by_component_id: dict[str, set[ArcKey]] = defaultdict(set)
    for index, (signature, component_arcs) in enumerate(component_specs, start=1):
        component_id = f"line{index}"
        activation_groups = _topologically_sorted_activation_groups(signature)
        activation_groups_by_component_id[component_id] = activation_groups
        roots, leaves = _root_and_leaf_ports_for_component(component_arcs)
        root_ports_by_component_id[component_id] = roots
        leaf_ports_by_component_id[component_id] = leaves
        for arc_key in component_arcs:
            component_id_by_arc[arc_key] = component_id
            source_node_ids_by_component_id[component_id].update(source_node_ids_by_arc[arc_key])
            component_arcs_by_component_id[component_id].add(arc_key)

    predecessor_groups_by_component_id: dict[str, dict[ActivationGroup, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    sink_line_groups_by_point_id: dict[str, dict[ActivationGroup, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for requirement_id, route_plan_arcs in route_plan_arcs_by_requirement_id.items():
        compiled_requirement = route_requirements_by_id[requirement_id]
        activation_group = activation_group_by_requirement_id[requirement_id]
        component_sequence = _compress_component_sequence(
            tuple(component_id_by_arc[arc_key] for arc_key in route_plan_arcs)
        )
        for previous_component_id, current_component_id in zip(
            component_sequence,
            component_sequence[1:],
        ):
            predecessor_groups_by_component_id[current_component_id][activation_group].add(
                previous_component_id
            )
        if component_sequence:
            sink_line_groups_by_point_id[str(compiled_requirement.sink_node_id)][activation_group].add(
                component_sequence[-1]
            )

    incoming_source_skills_by_gate_id = _incoming_source_skill_ids_by_gate_id(run_result)
    node_kinds = _node_kinds_by_node_id(run_result)
    for component_id, source_node_ids in source_node_ids_by_component_id.items():
        if len(source_node_ids) != 1:
            continue
        source_node_id = NodeId(next(iter(source_node_ids)))
        if node_kinds.get(source_node_id) != V1_AND_KNOT_KIND:
            continue
        activation_groups = activation_groups_by_component_id[component_id]
        if len(activation_groups) != 1:
            continue
        gate_inputs = incoming_source_skills_by_gate_id.get(source_node_id)
        if not gate_inputs:
            continue
        predecessor_component_ids: set[str] = set()
        for requirement_id, compiled_requirement in route_requirements_by_id.items():
            if compiled_requirement.sink_node_id != source_node_id:
                continue
            route_plan_arcs = route_plan_arcs_by_requirement_id.get(requirement_id, ())
            if not route_plan_arcs:
                continue
            predecessor_component_ids.add(component_id_by_arc[route_plan_arcs[-1]])
        if predecessor_component_ids:
            predecessor_groups_by_component_id[component_id][activation_groups[0]].update(
                predecessor_component_ids
            )

    sink_point_ids_by_component_id: dict[str, tuple[str, ...]] = {}
    for component_id in activation_groups_by_component_id:
        sink_point_ids_by_component_id[component_id] = tuple(
            sorted(
                point_id
                for point_id, dependency_groups in sink_line_groups_by_point_id.items()
                for group, line_ids in dependency_groups.items()
                if component_id in line_ids and group in activation_groups_by_component_id[component_id]
            )
        )

    removed_component_ids: set[str] = set()
    for component_id, activation_groups in list(activation_groups_by_component_id.items()):
        unique_sink_point_ids = tuple(sorted(set(sink_point_ids_by_component_id.get(component_id, ()))))
        if len(activation_groups) < 2:
            continue
        if any(len(group) != 1 for group in activation_groups):
            continue
        if len(unique_sink_point_ids) != 1:
            continue
        predecessor_map = predecessor_groups_by_component_id[component_id]
        if not predecessor_map:
            continue
        if any(len(predecessor_map.get(group, set())) != 1 for group in activation_groups):
            continue

        component_arc_keys = tuple(component_arcs_by_component_id[component_id])
        for activation_group in activation_groups:
            predecessor_component_id = next(iter(predecessor_map[activation_group]))
            component_arcs_by_component_id[predecessor_component_id].update(component_arc_keys)
            sink_line_groups_by_point_id[unique_sink_point_ids[0]][activation_group].discard(component_id)
            sink_line_groups_by_point_id[unique_sink_point_ids[0]][activation_group].add(
                predecessor_component_id
            )
        removed_component_ids.add(component_id)

    for component_id in removed_component_ids:
        activation_groups_by_component_id.pop(component_id, None)
        source_node_ids_by_component_id.pop(component_id, None)
        root_ports_by_component_id.pop(component_id, None)
        leaf_ports_by_component_id.pop(component_id, None)
        component_arcs_by_component_id.pop(component_id, None)
        predecessor_groups_by_component_id.pop(component_id, None)
        sink_point_ids_by_component_id.pop(component_id, None)

    for component_id, component_arc_keys in component_arcs_by_component_id.items():
        roots, leaves = _root_and_leaf_ports_for_component(frozenset(component_arc_keys))
        root_ports_by_component_id[component_id] = roots
        leaf_ports_by_component_id[component_id] = leaves

    point_specs: list[GlowPointSpec] = []
    for skill in sorted(
        run_result.requirement_spec.skills,
        key=lambda item: (item.tier, item.slot, item.skill_id),
    ):
        resolved_point = resolved_points[skill.skill_id]
        point_dependency_groups = tuple(tuple(group) for group in skill.requires)
        line_dependency_groups = tuple(
            tuple(
                sorted(
                    sink_line_groups_by_point_id[skill.skill_id].get(tuple(group), set())
                )
            )
            for group in skill.requires
            if sink_line_groups_by_point_id[skill.skill_id].get(tuple(group), set())
        )
        point_specs.append(
            GlowPointSpec(
                point_id=skill.skill_id,
                anchor_x=resolved_point.anchor_x,
                anchor_y=resolved_point.anchor_y,
                point_dependency_groups=point_dependency_groups,
                line_dependency_groups=line_dependency_groups,
                display_name=skill.name,
            )
        )

    sections: list[GlowSection] = []
    for component_id in sorted(
        activation_groups_by_component_id,
        key=lambda value: int(value.removeprefix("line")),
    ):
        activation_groups = activation_groups_by_component_id[component_id]
        line_dependency_groups = tuple(
            tuple(sorted(predecessor_groups_by_component_id[component_id].get(group, set())))
            for group in activation_groups
            if predecessor_groups_by_component_id[component_id].get(group, set())
        )
        sink_point_ids = tuple(
            sorted(
                point_id
                for point_id, dependency_groups in sink_line_groups_by_point_id.items()
                for group, line_ids in dependency_groups.items()
                if component_id in line_ids and group in activation_groups
            )
        )
        draw_knot = any(len(group) > 1 for group in activation_groups) and bool(line_dependency_groups)
        sections.append(
            GlowSection(
                section_id=component_id,
                arc_keys=frozenset(component_arcs_by_component_id[component_id]),
                activation_groups=activation_groups,
                line_dependency_groups=line_dependency_groups,
                sink_point_ids=sink_point_ids,
                draw_knot=draw_knot,
                root_port_refs=root_ports_by_component_id[component_id],
                leaf_port_refs=leaf_ports_by_component_id[component_id],
            )
        )

    return GlowSectionBuildResult(
        point_specs=tuple(point_specs),
        sections=tuple(sections),
    )


def build_glow_port_pixel_lookup_for_successful_run(
    run_result: SkillTreeRunResult,
    *,
    render_layout_profile: RenderLayoutProfile | None = None,
) -> dict[PortRef, tuple[int, int]]:
    """Return resolved port pixel positions for a successful run."""

    return _port_pixel_lookup_for_resolved_state(
        run_result,
        render_layout_profile=render_layout_profile,
    )
