import unittest

from toolsv2.profile import LogicalToPixelMapper
from toolsv2.solver_common import PortId, RenderProfileKey
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    CompositionOperatorId,
    ConnectionFamilyKey,
    DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,
    DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
    InternalTransitionSpec,
    LocalFootprint,
    LogicalToRenderMapper,
    PortGeometrySpec,
    RenderLayerSpec,
    RenderStyleProfile,
    RenderTemplateBinding,
    RenderTemplateKey,
    RenderTemplateSpec,
    StaticVisualProfileCatalog,
    VisualLayerId,
    build_v1_plain_junction_visual_profile_catalog,
)


class TestVisualProfiles(unittest.TestCase):
    def test_profile_mapper_alias_uses_visual_contract(self) -> None:
        self.assertIs(LogicalToPixelMapper, LogicalToRenderMapper)

    def test_build_geometry_profile_accepts_ports_and_internal_transitions(self) -> None:
        profile = BuildGeometryProfile(
            profile_key=RenderProfileKey("junction/plain"),
            footprint=LocalFootprint(width=5, height=5),
            ports=(
                PortGeometrySpec(
                    port_id=PortId("north"),
                    offset_x=2,
                    offset_y=0,
                    attach_direction="north",
                    connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                ),
                PortGeometrySpec(
                    port_id=PortId("south"),
                    offset_x=2,
                    offset_y=4,
                    attach_direction="south",
                    connection_family_keys=(ConnectionFamilyKey("road_basic"),),
                ),
            ),
            internal_transitions=(
                InternalTransitionSpec(
                    from_port_id=PortId("north"),
                    to_port_id=PortId("south"),
                    connection_family_key=ConnectionFamilyKey("road_basic"),
                ),
            ),
        )

        self.assertEqual(RenderProfileKey("junction/plain"), profile.profile_key)
        self.assertEqual(2, len(profile.ports))
        self.assertEqual(1, len(profile.internal_transitions))

    def test_build_geometry_profile_rejects_transition_for_unknown_port(self) -> None:
        with self.assertRaises(ValueError):
            BuildGeometryProfile(
                profile_key=RenderProfileKey("junction/plain"),
                footprint=LocalFootprint(width=5, height=5),
                ports=(
                    PortGeometrySpec(
                        port_id=PortId("north"),
                        offset_x=2,
                        offset_y=0,
                        attach_direction="north",
                    ),
                ),
                internal_transitions=(
                    InternalTransitionSpec(
                        from_port_id=PortId("north"),
                        to_port_id=PortId("south"),
                        connection_family_key=ConnectionFamilyKey("road_basic"),
                    ),
                ),
            )

    def test_render_template_supports_pixel_masks_and_sprite_refs(self) -> None:
        pixel_mask = RenderTemplateSpec(
            template_key=RenderTemplateKey("road_vert"),
            kind="pixel_mask",
            pixel_rows=((0, 1, 2), (0, 1, 2), (0, 1, 2)),
        )
        sprite_ref = RenderTemplateSpec(
            template_key=RenderTemplateKey("node_skill"),
            kind="sprite_ref",
            asset_ref="objects/skill.png",
        )

        self.assertEqual("pixel_mask", pixel_mask.kind)
        self.assertEqual("sprite_ref", sprite_ref.kind)

    def test_render_template_rejects_non_rectangular_pixel_mask(self) -> None:
        with self.assertRaises(ValueError):
            RenderTemplateSpec(
                template_key=RenderTemplateKey("bad_mask"),
                kind="pixel_mask",
                pixel_rows=((0, 1), (0, 1, 2)),
            )

    def test_static_visual_profile_catalog_resolves_profiles_layers_and_templates(self) -> None:
        build_profile = BuildGeometryProfile(
            profile_key=RenderProfileKey("junction/plain"),
            footprint=LocalFootprint(width=5, height=5),
        )
        style_profile = RenderStyleProfile(
            profile_key=RenderProfileKey("junction/plain"),
            template_bindings=(
                RenderTemplateBinding(
                    layer_id=VisualLayerId("connections"),
                    template_key=RenderTemplateKey("road_vert"),
                ),
            ),
        )
        layer = RenderLayerSpec(
            layer_id=VisualLayerId("connections"),
            order=1,
            composition_operator=CompositionOperatorId("max_light"),
        )
        template = RenderTemplateSpec(
            template_key=RenderTemplateKey("road_vert"),
            kind="pixel_mask",
            pixel_rows=((0, 1, 2), (0, 1, 2), (0, 1, 2)),
        )
        catalog = StaticVisualProfileCatalog(
            build_geometry_profiles=(build_profile,),
            render_style_profiles=(style_profile,),
            render_layers=(layer,),
            render_templates=(template,),
        )

        self.assertIs(build_profile, catalog.build_geometry_profile(RenderProfileKey("junction/plain")))
        self.assertIs(style_profile, catalog.render_style_profile(RenderProfileKey("junction/plain")))
        self.assertIs(layer, catalog.render_layer_spec(VisualLayerId("connections")))
        self.assertIs(template, catalog.render_template_spec(RenderTemplateKey("road_vert")))

    def test_default_plain_junction_catalog_contains_cardinal_ports_and_transitions(self) -> None:
        catalog = build_v1_plain_junction_visual_profile_catalog()

        profile = catalog.build_geometry_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY)

        self.assertEqual(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY, profile.profile_key)
        self.assertEqual(
            {PortId("north"), PortId("south"), PortId("west"), PortId("east")},
            {port.port_id for port in profile.ports},
        )
        self.assertEqual(12, len(profile.internal_transitions))
        self.assertTrue(
            all(
                transition.connection_family_key == DEFAULT_PLAIN_CONNECTION_FAMILY_KEY
                for transition in profile.internal_transitions
            )
        )


if __name__ == "__main__":
    unittest.main()
