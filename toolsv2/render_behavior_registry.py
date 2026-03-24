"""External callable registry for render finalization and composition behavior."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol

from PIL import Image, ImageChops

from toolsv2.render_contracts import RenderInstruction, ResolvedObjectRenderSpec
from toolsv2.render_template_loader import LoadedRenderTemplate
from toolsv2.solver_common import RenderProfileKey
from toolsv2.visual_profiles import (
    COMPOSITION_MAX_LIGHT,
    COMPOSITION_OVERWRITE,
    CompositionOperatorId,
    VisualProfileCatalog,
)


class ObjectRenderFinalizer(Protocol):
    """Finalize one resolved object into one or more render-ready objects."""

    def __call__(
        self,
        resolved_object: ResolvedObjectRenderSpec,
        visual_profile_catalog: VisualProfileCatalog,
    ) -> tuple[ResolvedObjectRenderSpec, ...]:
        """Return finalized resolved objects."""


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


def _identity_finalizer(
    resolved_object: ResolvedObjectRenderSpec,
    visual_profile_catalog: VisualProfileCatalog,
) -> tuple[ResolvedObjectRenderSpec, ...]:
    del visual_profile_catalog
    return (resolved_object,)


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


@dataclass(frozen=True, slots=True)
class RenderBehaviorRegistry:
    """External callable registry used by the renderer core."""

    composition_rules_by_operator: Mapping[CompositionOperatorId, CompositionRule]
    object_finalizers_by_profile_key: Mapping[RenderProfileKey, ObjectRenderFinalizer] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "composition_rules_by_operator",
            MappingProxyType(dict(self.composition_rules_by_operator)),
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
    ) -> tuple[ResolvedObjectRenderSpec, ...]:
        finalizer = self.object_finalizers_by_profile_key.get(
            resolved_object.profile_key,
            _identity_finalizer,
        )
        return finalizer(resolved_object, visual_profile_catalog)


def build_v1_render_behavior_registry() -> RenderBehaviorRegistry:
    """Return the current external render-behavior registry."""

    return RenderBehaviorRegistry(
        composition_rules_by_operator={
            COMPOSITION_OVERWRITE: overwrite_composition_rule,
            COMPOSITION_MAX_LIGHT: max_light_composition_rule,
        }
    )
