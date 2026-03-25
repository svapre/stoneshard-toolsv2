"""Generic placement-candidate ranking contracts.

This module defines the thin callback surface used by pass-1 placement search
to rank already-legal candidate junctions without embedding content-specific
policy into generic solver-core search code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from toolsv2.solver_common import ActiveGridState, Junction, NodeId
from toolsv2.solver_types import NodeDomain


PlacementCandidateRanker = Callable[
    [ActiveGridState, NodeId, frozenset[Junction], Mapping[NodeId, NodeDomain], int],
    tuple[Junction, ...],
]

