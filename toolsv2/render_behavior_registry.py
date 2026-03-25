"""External callable registry for render finalization and composition behavior."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

from PIL import Image, ImageChops

from toolsv2.connection_core_geometry import (
    centered_local_top_left,
    local_connection_binding,
    repeated_local_top_left_positions,
)
from toolsv2.render_contracts import (
    RasterStampInstruction,
    RenderInstruction,
    ResolvedLocalConnectionSpec,
    ResolvedObjectRenderSpec,
    SpriteStampInstruction,
)
from toolsv2.render_template_loader import LoadedRenderTemplate, RenderTemplateLoader
from toolsv2.solver_common import RenderProfileKey
from toolsv2.visual_profiles import (
    COMPOSITION_MAX_LIGHT,
    COMPOSITION_OVERWRITE,
    CompositionOperatorId,
    FINALIZER_COMPOSE_LOCAL_BLOCK,
    ObjectFinalizerRuleId,
    VisualProfileCatalog,
)


class CompositionRule(Protocol):
    """Apply one loaded template to the canvas at one concrete top-left position."""

    def __call__(
        self,
        canvas: Image.Image,
        instruction: RenderInstruction,
        template: LoadedRenderTemplate,
        *,
        top_left_x: int,
        top_left_y: int,
    ) -> None:
        """Mutate the destination canvas in place."""


CompositionRuleResolver = Callable[[CompositionOperatorId], CompositionRule]


class ObjectFinalizerRule(Protocol):
    """Finalize one resolved object into generic render instructions."""

    def __call__(
        self,
        resolved_object: ResolvedObjectRenderSpec,
        visual_profile_catalog: VisualProfileCatalog,
        template_loader: RenderTemplateLoader,
        composition_rule_for: CompositionRuleResolver,
    ) -> tuple[RenderInstruction, ...]:
        """Return finalized render instructions for one object."""


def _clipped_source_region(
    canvas: Image.Image,
    template: LoadedRenderTemplate,
    *,
    top_left_x: int,
    top_left_y: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    left = max(0, top_left_x)
    top = max(0, top_left_y)
    right = min(canvas.width, top_left_x + template.width)
    bottom = min(canvas.height, top_left_y + template.height)
    if left >= right or top >= bottom:
        return None
    source_left = left - top_left_x
    source_top = top - top_left_y
    source_right = source_left + (right - left)
    source_bottom = source_top + (bottom - top)
    return (left, top, right, bottom), (source_left, source_top, source_right, source_bottom)


def overwrite_composition_rule(
    canvas: Image.Image,
    instruction: RenderInstruction,
    template: LoadedRenderTemplate,
    *,
    top_left_x: int,
    top_left_y: int,
) -> None:
    """Default alpha-overwrite composition for sprite assets."""

    del instruction
    if template.kind != "sprite_ref" or template.image is None:
        raise NotImplementedError("overwrite currently supports sprite_ref templates only")
    clipped = _clipped_source_region(
        canvas,
        template,
        top_left_x=top_left_x,
        top_left_y=top_left_y,
    )
    if clipped is None:
        return
    (left, top, right, bottom), source_box = clipped
    source = template.image.crop(source_box)
    canvas.alpha_composite(source, (left, top))


def max_light_composition_rule(
    canvas: Image.Image,
    instruction: RenderInstruction,
    template: LoadedRenderTemplate,
    *,
    top_left_x: int,
    top_left_y: int,
) -> None:
    """Default max-light composition for sprite assets."""

    del instruction
    if template.kind != "sprite_ref" or template.image is None:
        raise NotImplementedError("max_light currently supports sprite_ref templates only")
    clipped = _clipped_source_region(
        canvas,
        template,
        top_left_x=top_left_x,
        top_left_y=top_left_y,
    )
    if clipped is None:
        return
    (left, top, right, bottom), source_box = clipped
    source = template.image.crop(source_box)
    destination = canvas.crop((left, top, right, bottom))
    composited = ImageChops.lighter(destination, source)
    canvas.paste(composited, (left, top))


def _rgba_rows_from_image(
    image: Image.Image,
) -> tuple[tuple[tuple[int, int, int, int], ...], ...]:
    rgba_image = image.convert("RGBA")
    return tuple(
        tuple(rgba_image.getpixel((x, y)) for x in range(rgba_image.width))
        for y in range(rgba_image.height)
    )


def _placeholder_instruction(
    binding: RenderTemplateBinding,
    *,
    composition_operator: CompositionOperatorId,
) -> SpriteStampInstruction:
    return SpriteStampInstruction(
        layer_id=binding.layer_id,
        template_key=binding.template_key,
        anchor_x=0,
        anchor_y=0,
        composition_operator=composition_operator,
    )


def _object_origin(
    resolved_object: ResolvedObjectRenderSpec,
    *,
    width: int,
    height: int,
) -> tuple[int, int]:
    return (
        resolved_object.anchor_x - (width // 2),
        resolved_object.anchor_y - (height // 2),
    )


def _resolved_port_lookup(
    resolved_object: ResolvedObjectRenderSpec,
) -> dict[PortId, tuple[int, int]]:
    return {
        port.port_id: (port.pixel_x, port.pixel_y)
        for port in resolved_object.ports
    }


def compose_local_block_finalizer_rule(
    resolved_object: ResolvedObjectRenderSpec,
    visual_profile_catalog: VisualProfileCatalog,
    template_loader: RenderTemplateLoader,
    composition_rule_for: CompositionRuleResolver,
) -> tuple[RenderInstruction, ...]:
    """Compose one object-local block from profile-declared local-connection rules."""

    style_profile = visual_profile_catalog.render_style_profile(resolved_object.profile_key)
    if style_profile.local_composition_operator is None:
        raise ValueError(
            f"RenderStyleProfile {resolved_object.profile_key!r} requires local_composition_operator for compose_local_block"
        )
    build_profile = visual_profile_catalog.build_geometry_profile(resolved_object.profile_key)
    if build_profile.footprint.anchor_x != 0 or build_profile.footprint.anchor_y != 0:
        raise NotImplementedError(
            "compose_local_block currently requires zero local footprint anchor offsets"
        )

    if not resolved_object.local_connections:
        return ()

    local_width = build_profile.footprint.width
    local_height = build_profile.footprint.height
    object_origin_x, object_origin_y = _object_origin(
        resolved_object,
        width=local_width,
        height=local_height,
    )
    local_port_positions = {
        port_id: (pixel_x - object_origin_x, pixel_y - object_origin_y)
        for port_id, (pixel_x, pixel_y) in _resolved_port_lookup(resolved_object).items()
    }

    local_composition_rule = composition_rule_for(style_profile.local_composition_operator)
    local_canvases_by_layer: dict[str, Image.Image] = {}

    for local_connection in resolved_object.local_connections:
        binding = local_connection_binding(
            style_profile,
            from_port_id=local_connection.from_port_id,
            to_port_id=local_connection.to_port_id,
        )
        template_spec = visual_profile_catalog.render_template_spec(binding.template_key)
        loaded_template = template_loader.load(template_spec, binding.transform)
        if loaded_template.kind != "sprite_ref" or loaded_template.image is None:
            raise NotImplementedError("compose_local_block currently supports sprite_ref templates only")

        layer_canvas = local_canvases_by_layer.get(str(binding.layer_id))
        if layer_canvas is None:
            layer_canvas = Image.new("RGBA", (local_width, local_height), (0, 0, 0, 0))
            local_canvases_by_layer[str(binding.layer_id)] = layer_canvas

        from_position = local_port_positions.get(local_connection.from_port_id)
        to_position = local_port_positions.get(local_connection.to_port_id)
        if from_position is None or to_position is None:
            raise ValueError(
                f"Missing resolved local port positions for local connection {(local_connection.from_port_id, local_connection.to_port_id)!r}"
            )

        repeated_positions = repeated_local_top_left_positions(
            local_start_x=from_position[0],
            local_start_y=from_position[1],
            local_end_x=to_position[0],
            local_end_y=to_position[1],
            template=loaded_template,
            binding=binding,
        )
        if repeated_positions is None:
            positions = (
                centered_local_top_left(
                    local_canvas_width=local_width,
                    local_canvas_height=local_height,
                    template=loaded_template,
                    binding=binding,
                ),
            )
        else:
            positions = repeated_positions

        placeholder = _placeholder_instruction(
            binding,
            composition_operator=style_profile.local_composition_operator,
        )
        for top_left_x, top_left_y in positions:
            local_composition_rule(
                layer_canvas,
                placeholder,
                loaded_template,
                top_left_x=top_left_x,
                top_left_y=top_left_y,
            )

    finalized_instructions: list[RenderInstruction] = []
    for layer_id in sorted(
        local_canvases_by_layer,
        key=lambda current_layer_id: visual_profile_catalog.render_layer_spec(current_layer_id).order,
    ):
        layer_canvas = local_canvases_by_layer[layer_id]
        if layer_canvas.getbbox() is None:
            continue
        layer_spec = visual_profile_catalog.render_layer_spec(layer_id)
        finalized_instructions.append(
            RasterStampInstruction(
                layer_id=layer_spec.layer_id,
                origin_x=object_origin_x,
                origin_y=object_origin_y,
                rgba_rows=_rgba_rows_from_image(layer_canvas),
                composition_operator=layer_spec.composition_operator,
                attributes=resolved_object.attributes,
            )
        )
    return tuple(finalized_instructions)


@dataclass(frozen=True, slots=True)
class RenderBehaviorRegistry:
    """External callable registry used by the renderer core."""

    composition_rules_by_operator: Mapping[CompositionOperatorId, CompositionRule]
    object_finalizer_rules_by_id: Mapping[ObjectFinalizerRuleId, ObjectFinalizerRule] = ()
    object_finalizers_by_profile_key: Mapping[RenderProfileKey, ObjectFinalizerRule] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "composition_rules_by_operator",
            MappingProxyType(dict(self.composition_rules_by_operator)),
        )
        object.__setattr__(
            self,
            "object_finalizer_rules_by_id",
            MappingProxyType(dict(self.object_finalizer_rules_by_id)),
        )
        object.__setattr__(
            self,
            "object_finalizers_by_profile_key",
            MappingProxyType(dict(self.object_finalizers_by_profile_key)),
        )

    def composition_rule_for(self, operator: CompositionOperatorId) -> CompositionRule:
        try:
            return self.composition_rules_by_operator[operator]
        except KeyError as exc:
            raise KeyError(f"Unknown composition operator: {operator}") from exc

    def finalize_resolved_object(
        self,
        resolved_object: ResolvedObjectRenderSpec,
        visual_profile_catalog: VisualProfileCatalog,
        template_loader: RenderTemplateLoader,
    ) -> tuple[RenderInstruction, ...] | None:
        override_finalizer = self.object_finalizers_by_profile_key.get(resolved_object.profile_key)
        if override_finalizer is not None:
            return override_finalizer(
                resolved_object,
                visual_profile_catalog,
                template_loader,
                self.composition_rule_for,
            )

        try:
            style_profile = visual_profile_catalog.render_style_profile(resolved_object.profile_key)
        except KeyError:
            return None
        if style_profile.finalizer_rule_id is None:
            return None
        try:
            finalizer_rule = self.object_finalizer_rules_by_id[style_profile.finalizer_rule_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown object finalizer rule: {style_profile.finalizer_rule_id}"
            ) from exc
        return finalizer_rule(
            resolved_object,
            visual_profile_catalog,
            template_loader,
            self.composition_rule_for,
        )


def build_v1_render_behavior_registry() -> RenderBehaviorRegistry:
    """Return the current external render-behavior registry."""

    return RenderBehaviorRegistry(
        composition_rules_by_operator={
            COMPOSITION_OVERWRITE: overwrite_composition_rule,
            COMPOSITION_MAX_LIGHT: max_light_composition_rule,
        },
        object_finalizer_rules_by_id={
            FINALIZER_COMPOSE_LOCAL_BLOCK: compose_local_block_finalizer_rule,
        },
    )
