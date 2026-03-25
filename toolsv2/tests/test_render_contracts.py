import inspect
import unittest
from toolsv2.render_contracts import (
    PixelMaskStampInstruction,
    PrimitiveExpander,
    RasterStampInstruction,
    RenderResolver,
    RepeatedSpanInstruction,
    ResolvedLocalConnectionSpec,
    ResolvedObjectRenderSpec,
    ResolvedPortRenderSpec,
    ResolvedSpanSpec,
    SpriteStampInstruction,
)
from toolsv2.solver_types import PortEdgeId, PortId, RenderProfileKey
from toolsv2.visual_profiles import (
    COMPOSITION_MAX_LIGHT,
    ConnectionFamilyKey,
    DEFAULT_ROAD_LAYER_ID,
    RenderTransformSpec,
    RenderTemplateKey,
)


class TestRenderContracts(unittest.TestCase):
    def test_render_resolver_and_primitive_expander_are_thin_callables(self) -> None:
        resolver_signature = inspect.signature(RenderResolver.__call__)
        expander_signature = inspect.signature(PrimitiveExpander.__call__)

        self.assertEqual(
            ["self", "state", "mapper", "visual_profile_catalog"],
            list(resolver_signature.parameters),
        )
        self.assertEqual(
            ["self", "resolved_objects", "visual_profile_catalog"],
            list(expander_signature.parameters),
        )

    def test_resolved_object_render_spec_can_hold_ports_local_connections_and_spans(self) -> None:
        spec = ResolvedObjectRenderSpec(
            instance_ref=PortEdgeId("edge::a"),
            profile_key=RenderProfileKey("edge/straight"),
            anchor_x=10,
            anchor_y=20,
            ports=(
                ResolvedPortRenderSpec(
                    port_id=PortId("from"),
                    pixel_x=5,
                    pixel_y=20,
                    attach_direction="west",
                ),
                ResolvedPortRenderSpec(
                    port_id=PortId("to"),
                    pixel_x=15,
                    pixel_y=20,
                    attach_direction="east",
                ),
            ),
            local_connections=(
                ResolvedLocalConnectionSpec(
                    from_port_id=PortId("from"),
                    to_port_id=PortId("to"),
                    connection_family_key=ConnectionFamilyKey("road_junction_piece"),
                ),
            ),
            spans=(
                ResolvedSpanSpec(
                    connection_family_key=ConnectionFamilyKey("road_external_straight"),
                    start_x=5,
                    start_y=20,
                    end_x=15,
                    end_y=20,
                ),
            ),
        )

        self.assertEqual(RenderProfileKey("edge/straight"), spec.profile_key)
        self.assertEqual(2, len(spec.ports))
        self.assertEqual(1, len(spec.local_connections))
        self.assertEqual(1, len(spec.spans))

    def test_render_instructions_stay_generic(self) -> None:
        sprite = SpriteStampInstruction(
            layer_id=DEFAULT_ROAD_LAYER_ID,
            template_key=RenderTemplateKey("node_skill_body"),
            anchor_x=10,
            anchor_y=20,
        )
        mask = PixelMaskStampInstruction(
            layer_id=DEFAULT_ROAD_LAYER_ID,
            template_key=RenderTemplateKey("junction_ns"),
            origin_x=0,
            origin_y=0,
            composition_operator=COMPOSITION_MAX_LIGHT,
        )
        span = RepeatedSpanInstruction(
            layer_id=DEFAULT_ROAD_LAYER_ID,
            connection_family_key=ConnectionFamilyKey("road_external_straight"),
            template_key=RenderTemplateKey("road_vertical_1x3"),
            start_x=0,
            start_y=0,
            end_x=0,
            end_y=12,
        )
        raster = RasterStampInstruction(
            layer_id=DEFAULT_ROAD_LAYER_ID,
            origin_x=0,
            origin_y=0,
            rgba_rows=(((0, 0, 0, 0),),),
        )

        self.assertEqual(
            {
                "layer_id",
                "template_key",
                "anchor_x",
                "anchor_y",
                "transform",
                "composition_operator",
                "attributes",
            },
            set(sprite.__dataclass_fields__),
        )
        self.assertEqual(
            {
                "layer_id",
                "template_key",
                "origin_x",
                "origin_y",
                "transform",
                "composition_operator",
                "attributes",
            },
            set(mask.__dataclass_fields__),
        )
        self.assertEqual(
            {
                "layer_id",
                "connection_family_key",
                "template_key",
                "start_x",
                "start_y",
                "end_x",
                "end_y",
                "transform",
                "composition_operator",
                "attributes",
            },
            set(span.__dataclass_fields__),
        )
        self.assertEqual(
            {
                "layer_id",
                "origin_x",
                "origin_y",
                "rgba_rows",
                "composition_operator",
                "attributes",
            },
            set(raster.__dataclass_fields__),
        )
        self.assertEqual(RenderTransformSpec(), sprite.transform)
        self.assertEqual(RenderTransformSpec(), mask.transform)
        self.assertEqual(RenderTransformSpec(), span.transform)


if __name__ == "__main__":
    unittest.main()
