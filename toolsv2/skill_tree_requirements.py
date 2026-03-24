"""Current requirement-spec loader/compiler for skill-tree JSON input.

This module owns only the translation from the higher-level requirement JSON
shape into the current explicit ``GraphContentModel`` used by the solver.
It does not perform placement, routing, rendering, or file-export work.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from toolsv2.graph_content import (
    GraphContentModel,
    GraphContentNode,
    GraphContentOrderedSameRowGroup,
    GraphContentPortAttachmentRequirement,
    GraphContentRouteRequirement,
)
from toolsv2.production_family_catalog import (
    V1_AND_KNOT_BOTTOM_PORT_ID,
    V1_AND_KNOT_KIND,
    V1_AND_KNOT_LEFT_PORT_ID,
    V1_AND_KNOT_RIGHT_PORT_ID,
    V1_AND_KNOT_TOP_PORT_ID,
    V1_SKILL_FRAME_BOTTOM_PORT_ID,
    V1_SKILL_FRAME_KIND,
    V1_SKILL_FRAME_TOP_PORT_ID,
)
from toolsv2.solver_common import LogicalYRailId, NodeId, PortId, RoutingPolicy


@dataclass(frozen=True, slots=True)
class SkillTreeSkillSpec:
    """One skill entry from the current requirement JSON."""

    skill_id: str
    name: str
    tier: int
    slot: int
    requires: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.skill_id:
            raise ValueError("SkillTreeSkillSpec.skill_id must not be empty")
        if self.tier < 1:
            raise ValueError("SkillTreeSkillSpec.tier must be at least 1")
        if self.slot < 0:
            raise ValueError("SkillTreeSkillSpec.slot must be non-negative")
        normalized_groups: list[tuple[str, ...]] = []
        for group in self.requires:
            if not group:
                raise ValueError("SkillTreeSkillSpec.requires groups must not be empty")
            if len(group) != len(set(group)):
                raise ValueError("SkillTreeSkillSpec.requires groups must not repeat ids")
            normalized_groups.append(tuple(str(skill_id) for skill_id in group))
        object.__setattr__(self, "requires", tuple(normalized_groups))


@dataclass(frozen=True, slots=True)
class SkillTreeRequirementSpec:
    """The current requirement-spec JSON shape."""

    tree_id: str
    background_base: str | None
    skills: tuple[SkillTreeSkillSpec, ...]

    def __post_init__(self) -> None:
        if not self.tree_id:
            raise ValueError("SkillTreeRequirementSpec.tree_id must not be empty")
        skill_ids = tuple(skill.skill_id for skill in self.skills)
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("SkillTreeRequirementSpec.skills ids must be unique")

        skills_by_id = {skill.skill_id: skill for skill in self.skills}
        slots_by_tier: dict[int, set[int]] = {}
        for skill in self.skills:
            if skill.slot in slots_by_tier.setdefault(skill.tier, set()):
                raise ValueError(
                    f"Tier {skill.tier} contains duplicate slot {skill.slot}"
                )
            slots_by_tier[skill.tier].add(skill.slot)

            for group in skill.requires:
                for dependency_id in group:
                    if dependency_id not in skills_by_id:
                        raise ValueError(
                            f"Skill {skill.skill_id} depends on unknown skill {dependency_id}"
                        )
                    if dependency_id == skill.skill_id:
                        raise ValueError(
                            f"Skill {skill.skill_id} cannot depend on itself"
                        )
                    if skills_by_id[dependency_id].tier >= skill.tier:
                        raise ValueError(
                            f"Skill {skill.skill_id} depends on {dependency_id} in same/lower tier"
                        )


def load_skill_tree_requirement_spec(path: str | Path) -> SkillTreeRequirementSpec:
    """Load one current requirement-spec JSON file."""

    json_path = Path(path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Requirement JSON root must be an object")

    raw_skills = data.get("skills")
    if not isinstance(raw_skills, list):
        raise TypeError("Requirement JSON must contain a 'skills' list")

    skills = tuple(
        SkillTreeSkillSpec(
            skill_id=str(item["id"]),
            name=str(item.get("name", item["id"])),
            tier=int(item["tier"]),
            slot=int(item["slot"]),
            requires=tuple(
                tuple(str(skill_id) for skill_id in group)
                for group in item.get("requires", ())
            ),
        )
        for item in raw_skills
    )
    background_base = data.get("background_base")
    return SkillTreeRequirementSpec(
        tree_id=str(data["tree_id"]),
        background_base=None if background_base is None else str(background_base),
        skills=skills,
    )


def build_default_skill_tree_routing_policy() -> RoutingPolicy:
    """Return the current default policy used by the file runner."""

    return RoutingPolicy(
        policy_id="default_skill_tree_policy",
        rule_values=(
            ("allow_move_north", True),
            ("allow_move_south", True),
            ("allow_move_east", True),
            ("allow_move_west", True),
        ),
    )


def authored_tier_rail_ids_for_tree(
    tree: SkillTreeRequirementSpec,
) -> tuple[LogicalYRailId, ...]:
    """Return the authored logical y-rail ids for this requirement tree."""

    max_tier = max((skill.tier for skill in tree.skills), default=0)
    if max_tier < 1:
        raise ValueError("SkillTreeRequirementSpec must contain at least one skill")
    return tuple(LogicalYRailId(f"tier_{index}") for index in range(max_tier))


def _group_skill_ids_by_tier(
    tree: SkillTreeRequirementSpec,
) -> dict[int, tuple[str, ...]]:
    grouped: dict[int, list[SkillTreeSkillSpec]] = {}
    for skill in tree.skills:
        grouped.setdefault(skill.tier, []).append(skill)
    return {
        tier: tuple(
            skill.skill_id
            for skill in sorted(skills, key=lambda item: (item.slot, item.skill_id))
        )
        for tier, skills in grouped.items()
    }


def _ordered_gate_sources(
    source_ids: tuple[str, ...],
    *,
    skills_by_id: dict[str, SkillTreeSkillSpec],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            source_ids,
            key=lambda skill_id: (
                skills_by_id[skill_id].tier,
                skills_by_id[skill_id].slot,
                skill_id,
            ),
        )
    )


def _and_gate_input_port_map(
    ordered_source_ids: tuple[str, ...],
) -> dict[str, PortId]:
    if len(ordered_source_ids) == 2:
        input_ports = (
            V1_AND_KNOT_LEFT_PORT_ID,
            V1_AND_KNOT_RIGHT_PORT_ID,
        )
    elif len(ordered_source_ids) == 3:
        input_ports = (
            V1_AND_KNOT_LEFT_PORT_ID,
            V1_AND_KNOT_TOP_PORT_ID,
            V1_AND_KNOT_RIGHT_PORT_ID,
        )
    else:
        raise ValueError(
            "Current v1 requirement compiler supports only 2- or 3-input AND groups"
        )
    return {
        source_id: port_id
        for source_id, port_id in zip(ordered_source_ids, input_ports)
    }


def _background_asset_ref(background_base: str | None) -> str | None:
    if background_base is None:
        return None
    if "/" in background_base or "\\" in background_base:
        return background_base.replace("\\", "/")
    return f"art/source/background/base/{background_base}"


@dataclass(frozen=True, slots=True)
class CompiledSkillTreeContent:
    """Compiled solver-facing content plus simple runner metadata."""

    tree_id: str
    graph_content: GraphContentModel
    authored_tier_rail_ids: tuple[LogicalYRailId, ...]
    background_asset_ref: str | None = None


def compile_v1_skill_tree_to_graph_content(
    tree: SkillTreeRequirementSpec,
) -> CompiledSkillTreeContent:
    """Compile the current requirement JSON shape into solver graph content."""

    skills_by_id = {skill.skill_id: skill for skill in tree.skills}
    authored_tier_rail_ids = authored_tier_rail_ids_for_tree(tree)

    nodes: list[GraphContentNode] = [
        GraphContentNode(
            node_id=NodeId(skill.skill_id),
            kind=V1_SKILL_FRAME_KIND,
            authored_tier_y_rail_id=LogicalYRailId(f"tier_{skill.tier - 1}"),
        )
        for skill in sorted(tree.skills, key=lambda item: (item.tier, item.slot, item.skill_id))
    ]
    ordered_same_row_groups = tuple(
        GraphContentOrderedSameRowGroup(
            ordered_node_ids=tuple(NodeId(skill_id) for skill_id in ordered_skill_ids)
        )
        for tier, ordered_skill_ids in sorted(_group_skill_ids_by_tier(tree).items())
        if len(ordered_skill_ids) > 1
    )

    route_requirements: list[GraphContentRouteRequirement] = []
    screening_port_requirements: list[GraphContentPortAttachmentRequirement] = []

    requirement_index = 0

    def _next_requirement_id(label: str) -> str:
        nonlocal requirement_index
        requirement_id = f"req::{requirement_index:04d}::{label}"
        requirement_index += 1
        return requirement_id

    grouped_multi_input_requirements: dict[tuple[int, tuple[str, ...]], list[str]] = {}
    for skill in tree.skills:
        for group in skill.requires:
            if len(group) > 1:
                key = (skill.tier, tuple(sorted(group)))
                grouped_multi_input_requirements.setdefault(key, []).append(skill.skill_id)

    for (sink_tier, source_ids), sink_ids in sorted(grouped_multi_input_requirements.items()):
        ordered_source_ids = _ordered_gate_sources(source_ids, skills_by_id=skills_by_id)
        gate_id = NodeId(f"node__req__tier{sink_tier}__{'__'.join(ordered_source_ids)}")
        nodes.append(
            GraphContentNode(
                node_id=gate_id,
                kind=V1_AND_KNOT_KIND,
            )
        )
        port_map = _and_gate_input_port_map(ordered_source_ids)
        for source_id in ordered_source_ids:
            gate_input_port_id = port_map[source_id]
            route_requirements.append(
                GraphContentRouteRequirement(
                    requirement_id=_next_requirement_id(f"{source_id}__to__{gate_id}"),
                    source_node_id=NodeId(source_id),
                    sink_node_id=gate_id,
                    requirement_kind="flow",
                    source_port_ids=(V1_SKILL_FRAME_BOTTOM_PORT_ID,),
                    sink_port_ids=(gate_input_port_id,),
                )
            )
            screening_port_requirements.append(
                GraphContentPortAttachmentRequirement(
                    node_id=gate_id,
                    port_id=gate_input_port_id,
                    required_attachments=1,
                )
            )

        for sink_id in sorted(set(sink_ids)):
            route_requirements.append(
                GraphContentRouteRequirement(
                    requirement_id=_next_requirement_id(f"{gate_id}__to__{sink_id}"),
                    source_node_id=gate_id,
                    sink_node_id=NodeId(sink_id),
                    requirement_kind="flow",
                    source_port_ids=(V1_AND_KNOT_BOTTOM_PORT_ID,),
                    sink_port_ids=(V1_SKILL_FRAME_TOP_PORT_ID,),
                )
            )

    for skill in tree.skills:
        for group in skill.requires:
            if len(group) != 1:
                continue
            source_id = group[0]
            route_requirements.append(
                GraphContentRouteRequirement(
                    requirement_id=_next_requirement_id(f"{source_id}__to__{skill.skill_id}"),
                    source_node_id=NodeId(source_id),
                    sink_node_id=NodeId(skill.skill_id),
                    requirement_kind="flow",
                    source_port_ids=(V1_SKILL_FRAME_BOTTOM_PORT_ID,),
                    sink_port_ids=(V1_SKILL_FRAME_TOP_PORT_ID,),
                )
            )

    return CompiledSkillTreeContent(
        tree_id=tree.tree_id,
        graph_content=GraphContentModel(
            routing_policy=build_default_skill_tree_routing_policy(),
            nodes=tuple(nodes),
            route_requirements=tuple(route_requirements),
            screening_port_requirements=tuple(screening_port_requirements),
            ordered_same_row_groups=ordered_same_row_groups,
        ),
        authored_tier_rail_ids=authored_tier_rail_ids,
        background_asset_ref=_background_asset_ref(tree.background_base),
    )
