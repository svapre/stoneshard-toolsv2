"""Concrete primitive expander from resolved specs to generic instructions.

This module performs the second render-preparation layer:
- consume resolved object render specs
- look up static render style and connection-family data
- emit generic renderer instructions only

It intentionally does not composite pixels or export final images.
"""

from __future__ import annotations

from dataclasses import dataclass

from toolsv2.render_contracts import (
    PixelMaskStampInstruction,
    PrimitiveExpander,
    RenderInstruction,
    RepeatedSpanInstruction,
    ResolvedLocalConnectionSpec,
    ResolvedObjectRenderSpec,
    ResolvedSpanSpec,
    SpriteStampInstruction,
)
from toolsv2.visual_profiles import (
    ConnectionFamilyProfile,
    ConnectionFamilyKey,
    RenderStyleProfile,
    RenderTemplateBinding,
    RenderTransformSpec,
    RenderTemplateKey,
    VisualProfileCatalog,
)


def _span_template_key_for_axis_aligned_family(
    family_key: ConnectionFamilyKey,
    family_profile: ConnectionFamilyProfile,
    span: ResolvedSpanSpec,
) -> RenderTemplateKey:
    if family_profile.shape_kind != "axis_aligned_straight":
        raise ValueError(
            f"Connection family {family_key!r} does not describe axis-aligned straight spans"
        )
    if len(family_profile.template_keys) not in (1, 2):
        raise ValueError(
            f"Axis-aligned straight family {family_key!r} requires one canonical template or two oriented templates"
        )
    if len(family_profile.template_keys) == 1:
        return family_profile.template_keys[0]
    if span.start_y == span.end_y:
        return family_profile.template_keys[0]
    if span.start_x == span.end_x:
        return family_profile.template_keys[1]
    raise ValueError(f"Resolved span for family {family_key!r} is not axis aligned")


def _span_transform_for_axis_aligned_family(
    family_profile: ConnectionFamilyProfile,
    span: ResolvedSpanSpec,
) -> RenderTransformSpec:
    if len(family_profile.template_keys) == 2:
        return RenderTransformSpec()
    if span.start_y == span.end_y:
        return RenderTransformSpec(quarter_turns_clockwise=1)
    if span.start_x == span.end_x:
        return RenderTransformSpec()
    raise ValueError("Resolved span is not axis aligned")


def _expand_binding(
    binding: RenderTemplateBinding,
    *,
    anchor_x: int,
    anchor_y: int,
    attributes,
    visual_profile_catalog: VisualProfileCatalog,
) -> RenderInstruction:
    layer_spec = visual_profile_catalog.render_layer_spec(binding.layer_id)
    template_spec = visual_profile_catalog.render_template_spec(binding.template_key)
    if template_spec.kind == "sprite_ref":
        return SpriteStampInstruction(
            layer_id=binding.layer_id,
            template_key=binding.template_key,
            anchor_x=anchor_x + binding.offset_x,
            anchor_y=anchor_y + binding.offset_y,
            transform=binding.transform,
            composition_operator=layer_spec.composition_operator,
            attributes=attributes,
        )
    return PixelMaskStampInstruction(
        layer_id=binding.layer_id,
        template_key=binding.template_key,
        origin_x=anchor_x + binding.offset_x,
        origin_y=anchor_y + binding.offset_y,
        transform=binding.transform,
        composition_operator=layer_spec.composition_operator,
        attributes=attributes,
    )


def _expand_style_bindings(
    resolved_object: ResolvedObjectRenderSpec,
    visual_profile_catalog: VisualProfileCatalog,
) -> tuple[RenderInstruction, ...]:
    style_profile = visual_profile_catalog.render_style_profile(resolved_object.profile_key)
    instructions: list[RenderInstruction] = []
    for binding in style_profile.template_bindings:
        instructions.append(
            _expand_binding(
                binding,
                anchor_x=resolved_object.anchor_x,
                anchor_y=resolved_object.anchor_y,
                attributes=resolved_object.attributes,
                visual_profile_catalog=visual_profile_catalog,
            )
        )
    return tuple(instructions)


def _local_connection_binding(
    style_profile: RenderStyleProfile,
    local_connection: ResolvedLocalConnectionSpec,
) -> RenderTemplateBinding:
    expected_pair = frozenset((local_connection.from_port_id, local_connection.to_port_id))
    for local_connection_template in style_profile.local_connection_templates:
        if frozenset(local_connection_template.port_ids) == expected_pair:
            return local_connection_template.binding
    raise NotImplementedError(
        f"No local connection template binding is frozen for port pair {tuple(sorted(str(port_id) for port_id in expected_pair))}"
    )


def _expand_local_connection(
    resolved_object: ResolvedObjectRenderSpec,
    local_connection: ResolvedLocalConnectionSpec,
    visual_profile_catalog: VisualProfileCatalog,
) -> RenderInstruction:
    style_profile = visual_profile_catalog.render_style_profile(resolved_object.profile_key)
    family_profile = visual_profile_catalog.connection_family_profile(
        local_connection.connection_family_key
    )
    if family_profile.rule_kind != "local_connection_piece":
        raise ValueError(
            f"Local connection family {local_connection.connection_family_key!r} must use local_connection_piece"
        )
    binding = _local_connection_binding(style_profile, local_connection)
    if binding.layer_id != family_profile.layer_id:
        raise ValueError(
            f"Local connection binding layer {binding.layer_id!r} does not match family layer {family_profile.layer_id!r}"
        )
    return _expand_binding(
        binding,
        anchor_x=resolved_object.anchor_x,
        anchor_y=resolved_object.anchor_y,
        attributes=local_connection.attributes,
        visual_profile_catalog=visual_profile_catalog,
    )


def _expand_span(
    span: ResolvedSpanSpec,
    visual_profile_catalog: VisualProfileCatalog,
) -> RepeatedSpanInstruction:
    family_profile = visual_profile_catalog.connection_family_profile(span.connection_family_key)
    if family_profile.rule_kind != "repeat_span":
        raise ValueError(
            f"Span family {span.connection_family_key!r} must use repeat_span rule kind"
        )
    layer_spec = visual_profile_catalog.render_layer_spec(family_profile.layer_id)
    return RepeatedSpanInstruction(
        layer_id=family_profile.layer_id,
        connection_family_key=span.connection_family_key,
        template_key=_span_template_key_for_axis_aligned_family(
            span.connection_family_key,
            family_profile,
            span,
        ),
        start_x=span.start_x,
        start_y=span.start_y,
        end_x=span.end_x,
        end_y=span.end_y,
        transform=_span_transform_for_axis_aligned_family(family_profile, span),
        composition_operator=layer_spec.composition_operator,
        attributes=span.attributes,
    )


@dataclass(frozen=True, slots=True)
class V1PrimitiveExpander:
    """Expand resolved render specs into generic renderer instructions."""

    def __call__(
        self,
        resolved_objects: tuple[ResolvedObjectRenderSpec, ...],
        visual_profile_catalog: VisualProfileCatalog,
    ) -> tuple[RenderInstruction, ...]:
        instructions: list[RenderInstruction] = []
        for resolved_object in resolved_objects:
            try:
                instructions.extend(_expand_style_bindings(resolved_object, visual_profile_catalog))
            except KeyError:
                if resolved_object.spans or resolved_object.local_connections:
                    pass
                else:
                    raise
            for local_connection in resolved_object.local_connections:
                instructions.append(
                    _expand_local_connection(
                        resolved_object,
                        local_connection,
                        visual_profile_catalog,
                    )
                )
            for span in resolved_object.spans:
                instructions.append(_expand_span(span, visual_profile_catalog))
        return tuple(instructions)


def build_v1_primitive_expander() -> PrimitiveExpander:
    """Return the first concrete primitive expander."""

    return V1PrimitiveExpander()
