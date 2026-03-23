from __future__ import annotations

import unittest

from toolsv2.profile import build_minimum_active_grid
from toolsv2.screening import (
    PortAttachmentRequirement,
    screen_node_domain,
)
from toolsv2.solver_types import Junction, NodeDefinition, NodeDomain, NodeId, PortDefinition, PortId, RoutingPolicy


def _grid():
    return build_minimum_active_grid(
        default_x_rail_ids=("x0", "x1", "x2"),
        authored_tier_rail_ids=("tier_0", "tier_1"),
    )


def _policy(*, north: bool = True, south: bool = True, east: bool = True, west: bool = True) -> RoutingPolicy:
    return RoutingPolicy(
        policy_id="screening_policy",
        rule_values=(
            ("allow_move_north", north),
            ("allow_move_south", south),
            ("allow_move_east", east),
            ("allow_move_west", west),
        ),
    )


def _node_with_port(port_id: str, orientation: str, capacity: int = 1) -> NodeDefinition:
    return NodeDefinition(
        node_id=NodeId("screened"),
        kind="generic",
        ports=(
            PortDefinition(
                port_id=PortId(port_id),
                orientation=orientation,  # type: ignore[arg-type]
                capacity=capacity,
            ),
        ),
    )


def _domain(node_id: str, *junctions: Junction) -> NodeDomain:
    return NodeDomain(
        node_id=NodeId(node_id),
        junctions=frozenset(junctions),
    )


class ScreeningTests(unittest.TestCase):
    def test_candidate_survives_when_not_disproved(self) -> None:
        grid = _grid()
        candidate = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        domain = _domain("screened", candidate)
        result = screen_node_domain(
            active_grid=grid,
            routing_policy=_policy(),
            node_definition=_node_with_port("east_out", "east"),
            domain=domain,
            node_domains={NodeId("screened"): domain},
            requirements=(PortAttachmentRequirement(port_id=PortId("east_out")),),
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(frozenset({candidate}), result.domain.junctions)

    def test_candidate_is_removed_when_required_adjacent_port_site_does_not_exist(self) -> None:
        grid = _grid()
        candidate = Junction(grid.x_rails[2].rail_id, grid.y_rails[0].rail_id)
        domain = _domain("screened", candidate)
        result = screen_node_domain(
            active_grid=grid,
            routing_policy=_policy(),
            node_definition=_node_with_port("east_out", "east"),
            domain=domain,
            node_domains={NodeId("screened"): domain},
            requirements=(PortAttachmentRequirement(port_id=PortId("east_out")),),
        )

        self.assertTrue(result.has_contradiction)
        self.assertEqual(frozenset(), result.domain.junctions)

    def test_candidate_is_removed_when_node_occupancy_blocks_required_terminal_attachment(self) -> None:
        grid = _grid()
        candidate = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        blocked_site = Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id)
        target_domain = _domain("screened", candidate)
        occupied_domain = _domain("occupied", blocked_site)

        result = screen_node_domain(
            active_grid=grid,
            routing_policy=_policy(),
            node_definition=_node_with_port("east_out", "east"),
            domain=target_domain,
            node_domains={
                NodeId("screened"): target_domain,
                NodeId("occupied"): occupied_domain,
            },
            requirements=(PortAttachmentRequirement(port_id=PortId("east_out")),),
        )

        self.assertTrue(result.has_contradiction)
        self.assertEqual(frozenset(), result.domain.junctions)

    def test_screening_ignores_non_node_junction_connection_state(self) -> None:
        grid = _grid()
        candidate = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        domain = _domain("screened", candidate)
        ignored_state = {
            Junction(grid.x_rails[1].rail_id, grid.y_rails[0].rail_id): {"roads": "blocked", "connections": ("east", "west")},
        }

        result = screen_node_domain(
            active_grid=grid,
            routing_policy=_policy(),
            node_definition=_node_with_port("east_out", "east"),
            domain=domain,
            node_domains={NodeId("screened"): domain},
            requirements=(PortAttachmentRequirement(port_id=PortId("east_out")),),
            non_node_connection_state=ignored_state,
        )

        self.assertFalse(result.has_contradiction)
        self.assertEqual(frozenset({candidate}), result.domain.junctions)

    def test_unsupported_open_screening_case_fails_loudly(self) -> None:
        grid = _grid()
        candidate = Junction(grid.x_rails[0].rail_id, grid.y_rails[0].rail_id)
        domain = _domain("screened", candidate)

        with self.assertRaises(NotImplementedError):
            screen_node_domain(
                active_grid=grid,
                routing_policy=_policy(),
                node_definition=_node_with_port("east_out", "east", capacity=2),
                domain=domain,
                node_domains={NodeId("screened"): domain},
                requirements=(PortAttachmentRequirement(port_id=PortId("east_out"), required_attachments=2),),
            )


if __name__ == "__main__":
    unittest.main()

