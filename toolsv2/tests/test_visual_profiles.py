import unittest

from toolsv2.profile import LogicalToPixelMapper
from toolsv2.solver_common import PortId, RenderProfileKey
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    COMPOSITION_MAX_LIGHT,
    COMPOSITION_OVERWRITE,
    CompositionOperatorId,
    ConnectionFamilyKey,
    ConnectionFamilyProfile,
    DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
    DEFAULT_AND_KNOT_PROFILE_KEY,
    DEFAULT_BACKGROUND_LAYER_ID,
    DEFAULT_EXTERNAL_STRAIGHT_HORIZONTAL_TEMPLATE_KEY,
    DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
    DEFAULT_EXTERNAL_STRAIGHT_VERTICAL_TEMPLATE_KEY,
    DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
    DEFAULT_SKILL_FRAME_PROFILE_KEY,
    DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
    DEFAULT_PLAIN_CONNECTION_FAMILY_KEY,
    DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY,
    DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
    DEFAULT_ROAD_LAYER_ID,
    DEFAULT_SHADOW_LAYER_ID,
    DEFAULT_OBJECT_BODY_LAYER_ID,
    DEFAULT_OBJECT_FOREGROUND_LAYER_ID,
    FINALIZER_COMPOSE_LOCAL_BLOCK,
    InternalTransitionSpec,
    JunctionPatternOverrideSpec,
    LocalConnectionTemplateSpec,
    LocalFootprint,
    LogicalToRenderMapper,
    PortGeometrySpec,
    RenderLayerSpec,
    RenderStyleProfile,
    RenderTemplateBinding,
    RenderTransformSpec,
    RenderTemplateKey,
    RenderTemplateSpec,
    StaticVisualProfileCatalog,
    VisualLayerId,
    build_v1_and_knot_build_geometry_profile,
    build_v1_and_knot_render_style_profile,
    build_v1_core_render_templates,
    build_v1_core_visual_profile_catalog,
    build_v1_default_render_layers,
    build_v1_plain_junction_visual_profile_catalog,
    build_v1_skill_frame_build_geometry_profile,
    build_v1_skill_frame_render_style_profile,
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

    def test_render_style_profile_accepts_future_junction_pattern_override_data(self) -> None:
        profile = RenderStyleProfile(
            profile_key=RenderProfileKey("junction/plain"),
            local_connection_templates=(
                LocalConnectionTemplateSpec(
                    port_ids=(PortId("north"), PortId("south")),
                    binding=RenderTemplateBinding(
                        layer_id=VisualLayerId("connections"),
                        template_key=RenderTemplateKey("road_straight"),
                        transform=RenderTransformSpec(quarter_turns_clockwise=1),
                    ),
                ),
            ),
            connection_pattern_overrides=(
                JunctionPatternOverrideSpec(
                    engaged_port_ids=(PortId("north"), PortId("south"), PortId("east")),
                ),
            ),
        )

        self.assertEqual(1, len(profile.local_connection_templates))
        self.assertEqual(1, len(profile.connection_pattern_overrides))

    def test_connection_family_profile_captures_rule_kind_and_layer(self) -> None:
        profile = ConnectionFamilyProfile(
            family_key=ConnectionFamilyKey("road_external_straight"),
            rule_kind="repeat_span",
            shape_kind="axis_aligned_straight",
            layer_id=VisualLayerId("road"),
        )

        self.assertEqual("repeat_span", profile.rule_kind)
        self.assertEqual(VisualLayerId("road"), profile.layer_id)

    def test_default_render_layers_use_shared_absolute_ordering(self) -> None:
        layers = build_v1_default_render_layers()

        self.assertEqual(
            (
                DEFAULT_BACKGROUND_LAYER_ID,
                DEFAULT_SHADOW_LAYER_ID,
                DEFAULT_ROAD_LAYER_ID,
                DEFAULT_OBJECT_BODY_LAYER_ID,
                DEFAULT_OBJECT_FOREGROUND_LAYER_ID,
            ),
            tuple(layer.layer_id for layer in layers),
        )
        self.assertEqual((0, 1, 3, 4, 5), tuple(layer.order for layer in layers))
        self.assertEqual(
            (
                COMPOSITION_OVERWRITE,
                COMPOSITION_OVERWRITE,
                COMPOSITION_OVERWRITE,
                COMPOSITION_OVERWRITE,
                COMPOSITION_OVERWRITE,
            ),
            tuple(layer.composition_operator for layer in layers),
        )

    def test_default_plain_junction_catalog_contains_cardinal_ports_and_transitions(self) -> None:
        catalog = build_v1_plain_junction_visual_profile_catalog()

        profile = catalog.build_geometry_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY)

        self.assertEqual(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY, profile.profile_key)
        self.assertEqual(
            {PortId("north"), PortId("south"), PortId("west"), PortId("east")},
            {port.port_id for port in profile.ports},
        )
        self.assertEqual(
            {
                PortId("north"): (0, -2),
                PortId("south"): (0, 2),
                PortId("west"): (-2, 0),
                PortId("east"): (2, 0),
            },
            {port.port_id: (port.offset_x, port.offset_y) for port in profile.ports},
        )
        self.assertEqual(12, len(profile.internal_transitions))
        junction_style = catalog.render_style_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY)
        self.assertEqual(6, len(junction_style.local_connection_templates))
        self.assertEqual(FINALIZER_COMPOSE_LOCAL_BLOCK, junction_style.finalizer_rule_id)
        self.assertEqual(COMPOSITION_MAX_LIGHT, junction_style.local_composition_operator)
        bindings_by_pair = {
            frozenset(template.port_ids): template.binding
            for template in junction_style.local_connection_templates
        }
        self.assertEqual(
            0,
            bindings_by_pair[frozenset((PortId("north"), PortId("south")))].transform.quarter_turns_clockwise,
        )
        self.assertEqual(
            1,
            bindings_by_pair[frozenset((PortId("west"), PortId("east")))].transform.quarter_turns_clockwise,
        )
        self.assertTrue(
            all(
                transition.connection_family_key == DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY
                for transition in profile.internal_transitions
            )
        )
        self.assertEqual(
            "repeat_span",
            catalog.connection_family_profile(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY).rule_kind,
        )
        self.assertEqual(
            "axis_aligned_straight",
            catalog.connection_family_profile(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY).shape_kind,
        )
        self.assertEqual(
            "local_connection_piece",
            catalog.connection_family_profile(
                DEFAULT_JUNCTION_PIECE_CONNECTION_FAMILY_KEY
            ).rule_kind,
        )

    def test_skill_frame_profile_builder_uses_centered_ports_and_layered_sprites(self) -> None:
        build_profile = build_v1_skill_frame_build_geometry_profile(
            top_port_id=PortId("input_top"),
            bottom_port_id=PortId("output_bottom"),
        )
        style_profile = build_v1_skill_frame_render_style_profile()

        self.assertEqual(DEFAULT_SKILL_FRAME_PROFILE_KEY, build_profile.profile_key)
        self.assertEqual((31, 31), (build_profile.footprint.width, build_profile.footprint.height))
        self.assertEqual(
            {
                PortId("input_top"): (0, -15, "north"),
                PortId("output_bottom"): (0, 14, "south"),
            },
            {
                port.port_id: (port.offset_x, port.offset_y, port.attach_direction)
                for port in build_profile.ports
            },
        )
        self.assertEqual(
            (
                (DEFAULT_SHADOW_LAYER_ID, DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY, 0, 15),
                (DEFAULT_OBJECT_BODY_LAYER_ID, DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY, 0, 0),
            ),
            tuple(
                (binding.layer_id, binding.template_key, binding.offset_x, binding.offset_y)
                for binding in style_profile.template_bindings
            ),
        )

    def test_and_knot_profile_builder_uses_centered_ports_and_body_layer(self) -> None:
        build_profile = build_v1_and_knot_build_geometry_profile(
            top_port_id=PortId("in_top"),
            left_port_id=PortId("in_left"),
            right_port_id=PortId("in_right"),
            bottom_port_id=PortId("out_bottom"),
        )
        style_profile = build_v1_and_knot_render_style_profile()

        self.assertEqual(DEFAULT_AND_KNOT_PROFILE_KEY, build_profile.profile_key)
        self.assertEqual((5, 7), (build_profile.footprint.width, build_profile.footprint.height))
        self.assertEqual(
            {
                PortId("in_top"): (0, -2, "north"),
                PortId("in_left"): (-1, 0, "west"),
                PortId("in_right"): (1, 0, "east"),
                PortId("out_bottom"): (0, 2, "south"),
            },
            {
                port.port_id: (port.offset_x, port.offset_y, port.attach_direction)
                for port in build_profile.ports
            },
        )
        self.assertEqual(
            (
                (DEFAULT_OBJECT_BODY_LAYER_ID, DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY, 0, 0),
            ),
            tuple(
                (binding.layer_id, binding.template_key, binding.offset_x, binding.offset_y)
                for binding in style_profile.template_bindings
            ),
        )

    def test_core_render_templates_capture_current_symbolic_asset_bindings(self) -> None:
        templates = build_v1_core_render_templates()

        self.assertEqual(
            {
                DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY,
                DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY,
                DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY,
                DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,
                DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY,
            },
            {template.template_key for template in templates},
        )
        self.assertEqual(
            {
                DEFAULT_SKILL_FRAME_BODY_TEMPLATE_KEY: "art/source/node/skill_frame/FRAME_ROOT.png",
                DEFAULT_SKILL_FRAME_SHADOW_TEMPLATE_KEY: "art/source/node/skill_frame/FRAME_ROOT_SHADOW.png",
                DEFAULT_AND_KNOT_BODY_TEMPLATE_KEY: "art/source/node/and_knot/GATE_AND.png",
                DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY: "art/source/connection/external_straight/NONDIR_PORTS_TB.png",
                DEFAULT_JUNCTION_CORNER_TEMPLATE_KEY: "art/source/connection/junction_piece/DIR_PORTS_TR_IN_T_OUT_R.png",
            },
            {
                template.template_key: template.asset_ref
                for template in templates
            },
        )

    def test_core_visual_profile_catalog_combines_junction_skill_and_and_knot_profiles(self) -> None:
        catalog = build_v1_core_visual_profile_catalog(
            skill_frame_top_port_id=PortId("skill_in"),
            skill_frame_bottom_port_id=PortId("skill_out"),
            and_knot_top_port_id=PortId("and_in_top"),
            and_knot_left_port_id=PortId("and_in_left"),
            and_knot_right_port_id=PortId("and_in_right"),
            and_knot_bottom_port_id=PortId("and_out_bottom"),
        )

        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY))
        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_SKILL_FRAME_PROFILE_KEY))
        self.assertIsNotNone(catalog.build_geometry_profile(DEFAULT_AND_KNOT_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_PLAIN_JUNCTION_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_SKILL_FRAME_PROFILE_KEY))
        self.assertIsNotNone(catalog.render_style_profile(DEFAULT_AND_KNOT_PROFILE_KEY))
        self.assertEqual(
            (DEFAULT_EXTERNAL_STRAIGHT_TEMPLATE_KEY,),
            catalog.connection_family_profile(DEFAULT_PLAIN_CONNECTION_FAMILY_KEY).template_keys,
        )


if __name__ == "__main__":
    unittest.main()
