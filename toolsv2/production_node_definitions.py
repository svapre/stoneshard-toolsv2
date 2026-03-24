"""Canonical v1 production node definitions bound through external catalogs.

This module preserves the stable public helpers used by the rest of the stack,
but the family-specific schema data and source-art layout now live in separate
catalog modules so future extensions do not require edits to generic core
loaders/profile code.
"""

from __future__ import annotations

from toolsv2.production_family_catalog import (
    V1_AND_KNOT_BOTTOM_PORT_ID,
    V1_AND_KNOT_KIND,
    V1_AND_KNOT_LEFT_PORT_ID,
    V1_AND_KNOT_RIGHT_PORT_ID,
    V1_AND_KNOT_TOP_PORT_ID,
    V1_SKILL_FRAME_BOTTOM_PORT_ID,
    V1_SKILL_FRAME_KIND,
    V1_SKILL_FRAME_TOP_PORT_ID,
    build_v1_production_node_family_catalog,
)
from toolsv2.production_visual_catalog import (
    build_v1_production_visual_profile_catalog as _build_v1_production_visual_profile_catalog,
)
from toolsv2.solver_common import NodeId
from toolsv2.solver_schema import NodeDefinition
from toolsv2.visual_profiles import StaticVisualProfileCatalog


def build_v1_skill_frame_node_definition(node_id: NodeId) -> NodeDefinition:
    """Return the canonical v1 skill-frame node definition for one node id."""

    return (
        build_v1_production_node_family_catalog()
        .family_spec(V1_SKILL_FRAME_KIND)
        .build_node_definition(node_id)
    )


def build_v1_and_knot_node_definition(node_id: NodeId) -> NodeDefinition:
    """Return the canonical v1 AND-knot node definition for one node id."""

    return (
        build_v1_production_node_family_catalog()
        .family_spec(V1_AND_KNOT_KIND)
        .build_node_definition(node_id)
    )


def build_v1_production_visual_profile_catalog() -> StaticVisualProfileCatalog:
    """Return the current concrete visual/build catalog for frozen v1 families."""

    return _build_v1_production_visual_profile_catalog()
