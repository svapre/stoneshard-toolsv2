from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolsv2.production_family_catalog import (
    V1_AND_KNOT_KIND,
    V1_SKILL_FRAME_KIND,
)
from toolsv2.skill_tree_requirements import (
    authored_tier_rail_ids_for_tree,
    compile_v1_skill_tree_to_graph_content,
    load_skill_tree_requirement_spec,
)
from toolsv2.solver_common import NodeId, PortId


class SkillTreeRequirementsTests(unittest.TestCase):
    def _write_tree_json(self, payload: dict) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "tree.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loader_reads_requirement_tree_json(self) -> None:
        tree = load_skill_tree_requirement_spec(
            self._write_tree_json(
                {
                    "tree_id": "simple_tree",
                    "background_base": "BASE_BACKGROUND.png",
                    "skills": [
                        {
                            "id": "a1",
                            "name": "A1",
                            "tier": 1,
                            "slot": 0,
                            "requires": [],
                        },
                    ],
                }
            )
        )

        self.assertEqual("simple_tree", tree.tree_id)
        self.assertEqual("BASE_BACKGROUND.png", tree.background_base)
        self.assertEqual(1, len(tree.skills))
        self.assertEqual("a1", tree.skills[0].skill_id)

    def test_compiler_builds_direct_skill_route_requirements(self) -> None:
        compiled = compile_v1_skill_tree_to_graph_content(
            load_skill_tree_requirement_spec(
                self._write_tree_json(
                    {
                        "tree_id": "direct_tree",
                        "skills": [
                            {
                                "id": "a1",
                                "name": "A1",
                                "tier": 1,
                                "slot": 0,
                                "requires": [],
                            },
                            {
                                "id": "b1",
                                "name": "B1",
                                "tier": 2,
                                "slot": 0,
                                "requires": [["a1"]],
                            },
                        ],
                    }
                )
            )
        )

        self.assertEqual(
            ("tier_0", "tier_1"),
            tuple(str(rail_id) for rail_id in compiled.authored_tier_rail_ids),
        )
        self.assertEqual(
            (V1_SKILL_FRAME_KIND, V1_SKILL_FRAME_KIND),
            tuple(node.kind for node in compiled.graph_content.nodes),
        )
        self.assertEqual(1, len(compiled.graph_content.route_requirements))
        requirement = compiled.graph_content.route_requirements[0]
        self.assertEqual(NodeId("a1"), requirement.source_node_id)
        self.assertEqual(NodeId("b1"), requirement.sink_node_id)
        self.assertEqual((PortId("bottom"),), requirement.source_port_ids)
        self.assertEqual((PortId("top"),), requirement.sink_port_ids)

    def test_compiler_shares_multi_input_and_gate_by_sink_tier_and_group(self) -> None:
        compiled = compile_v1_skill_tree_to_graph_content(
            load_skill_tree_requirement_spec(
                self._write_tree_json(
                    {
                        "tree_id": "shared_and_tree",
                        "skills": [
                            {
                                "id": "a1",
                                "name": "A1",
                                "tier": 1,
                                "slot": 0,
                                "requires": [],
                            },
                            {
                                "id": "b1",
                                "name": "B1",
                                "tier": 1,
                                "slot": 1,
                                "requires": [],
                            },
                            {
                                "id": "x2",
                                "name": "X2",
                                "tier": 2,
                                "slot": 0,
                                "requires": [["a1", "b1"]],
                            },
                            {
                                "id": "y2",
                                "name": "Y2",
                                "tier": 2,
                                "slot": 1,
                                "requires": [["a1", "b1"]],
                            },
                        ],
                    }
                )
            )
        )

        and_nodes = [
            node
            for node in compiled.graph_content.nodes
            if node.kind == V1_AND_KNOT_KIND
        ]
        self.assertEqual(1, len(and_nodes))
        self.assertEqual(
            ("dyn::tier_0::tier_1::0", "dyn::tier_0::tier_1::1"),
            tuple(str(rail_id) for rail_id in and_nodes[0].allowed_y_rail_ids or ()),
        )
        self.assertEqual(4, len(compiled.graph_content.route_requirements))
        self.assertEqual(2, len(compiled.graph_content.screening_port_requirements))

    def test_authored_tier_rail_ids_cover_all_levels_up_to_max(self) -> None:
        tree = load_skill_tree_requirement_spec(
            self._write_tree_json(
                {
                    "tree_id": "tier_tree",
                    "skills": [
                        {
                            "id": "a1",
                            "name": "A1",
                            "tier": 1,
                            "slot": 0,
                            "requires": [],
                        },
                        {
                            "id": "c3",
                            "name": "C3",
                            "tier": 3,
                            "slot": 0,
                            "requires": [],
                        },
                    ],
                }
            )
        )

        self.assertEqual(
            ("tier_0", "tier_1", "tier_2"),
            tuple(str(rail_id) for rail_id in authored_tier_rail_ids_for_tree(tree)),
        )


if __name__ == "__main__":
    unittest.main()
