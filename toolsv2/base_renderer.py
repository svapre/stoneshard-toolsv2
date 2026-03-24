"""Concrete base renderer for the current committed-runtime render pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from toolsv2.primitive_expander import build_v1_primitive_expander
from toolsv2.render_behavior_registry import (
    RenderBehaviorRegistry,
    build_v1_render_behavior_registry,
)
from toolsv2.render_contracts import (
    PixelMaskStampInstruction,
    PrimitiveExpander,
    RenderInstruction,
    RenderResolver,
    RepeatedSpanInstruction,
    ResolvedObjectRenderSpec,
    SpriteStampInstruction,
)
from toolsv2.render_layout_profiles import (
    RenderLayoutProfile,
    build_v1_vanilla_render_layout_profile,
)
from toolsv2.render_resolver import build_v1_render_resolver
from toolsv2.render_template_loader import (
    RenderTemplateLoader,
    build_cached_render_template_loader,
)
from toolsv2.solver_runtime import PortGraphState
from toolsv2.visual_profiles import LogicalToRenderMapper, VisualProfileCatalog


def _instruction_sort_key(
    instruction: RenderInstruction,
    visual_profile_catalog: VisualProfileCatalog,
) -> tuple[int, int]:
    layer_spec = visual_profile_catalog.render_layer_spec(instruction.layer_id)
    return (layer_spec.order, 0)


def _instruction_anchor_top_left(
    instruction: SpriteStampInstruction,
    *,
    width: int,
    height: int,
) -> tuple[int, int]:
    return (
        instruction.anchor_x - (width // 2),
        instruction.anchor_y - (height // 2),
    )


def _repeat_span_centers(instruction: RepeatedSpanInstruction) -> tuple[tuple[int, int], ...]:
    if instruction.start_x != instruction.end_x and instruction.start_y != instruction.end_y:
        raise ValueError("RepeatedSpanInstruction must be axis aligned in the current renderer")
    dx = 0
    dy = 0
    if instruction.start_x < instruction.end_x:
        dx = 1
    elif instruction.start_x > instruction.end_x:
        dx = -1
    elif instruction.start_y < instruction.end_y:
        dy = 1
    else:
        dy = -1

    centers: list[tuple[int, int]] = []
    current_x = instruction.start_x
    current_y = instruction.start_y
    while True:
        centers.append((current_x, current_y))
        if current_x == instruction.end_x and current_y == instruction.end_y:
            break
        current_x += dx
        current_y += dy
    return tuple(centers)


def _blank_canvas(render_layout_profile: RenderLayoutProfile) -> Image.Image:
    return Image.new(
        "RGBA",
        (render_layout_profile.canvas_width, render_layout_profile.canvas_height),
        (0, 0, 0, 0),
    )


@dataclass(frozen=True, slots=True)
class BaseRenderResult:
    """One fully prepared base-render result."""

    image: Image.Image
    resolved_objects: tuple[ResolvedObjectRenderSpec, ...]
    instructions: tuple[RenderInstruction, ...]


@dataclass(slots=True)
class V1BaseRenderer:
    """Render one committed runtime snapshot into the base output image."""

    resolver: RenderResolver
    primitive_expander: PrimitiveExpander
    template_loader: RenderTemplateLoader
    behavior_registry: RenderBehaviorRegistry
    project_root: Path | None = None

    def __post_init__(self) -> None:
        if self.project_root is None:
            self.project_root = Path(__file__).resolve().parents[1]

    def _background_canvas(self, render_layout_profile: RenderLayoutProfile) -> Image.Image:
        if render_layout_profile.default_background_asset_ref is None:
            return _blank_canvas(render_layout_profile)
        background = self.template_loader.load_asset_rgba(
            render_layout_profile.default_background_asset_ref
        ).copy()
        if (
            background.width != render_layout_profile.canvas_width
            or background.height != render_layout_profile.canvas_height
        ):
            raise ValueError("Background asset size does not match render layout canvas size")
        return background

    def _compose_instruction(
        self,
        canvas: Image.Image,
        instruction: RenderInstruction,
        visual_profile_catalog: VisualProfileCatalog,
    ) -> None:
        if instruction.composition_operator is None:
            raise ValueError("RenderInstruction requires composition_operator for composition")
        composition_rule = self.behavior_registry.composition_rule_for(
            instruction.composition_operator
        )

        if isinstance(instruction, SpriteStampInstruction):
            template = self.template_loader.load(
                visual_profile_catalog.render_template_spec(instruction.template_key),
                instruction.transform,
            )
            top_left_x, top_left_y = _instruction_anchor_top_left(
                instruction,
                width=template.width,
                height=template.height,
            )
            composition_rule(
                canvas,
                instruction,
                template,
                top_left_x=top_left_x,
                top_left_y=top_left_y,
            )
            return

        if isinstance(instruction, PixelMaskStampInstruction):
            template = self.template_loader.load(
                visual_profile_catalog.render_template_spec(instruction.template_key),
                instruction.transform,
            )
            composition_rule(
                canvas,
                instruction,
                template,
                top_left_x=instruction.origin_x,
                top_left_y=instruction.origin_y,
            )
            return

        if isinstance(instruction, RepeatedSpanInstruction):
            template = self.template_loader.load(
                visual_profile_catalog.render_template_spec(instruction.template_key),
                instruction.transform,
            )
            for center_x, center_y in _repeat_span_centers(instruction):
                composition_rule(
                    canvas,
                    instruction,
                    template,
                    top_left_x=center_x - (template.width // 2),
                    top_left_y=center_y - (template.height // 2),
                )
            return

        raise TypeError(f"Unsupported render instruction type: {type(instruction)!r}")

    def __call__(
        self,
        state: PortGraphState,
        mapper: LogicalToRenderMapper,
        visual_profile_catalog: VisualProfileCatalog,
        *,
        render_layout_profile: RenderLayoutProfile | None = None,
    ) -> BaseRenderResult:
        if render_layout_profile is None:
            render_layout_profile = build_v1_vanilla_render_layout_profile()

        resolved_objects = self.resolver(
            state,
            mapper,
            visual_profile_catalog,
        )
        finalized_objects: list[ResolvedObjectRenderSpec] = []
        for resolved_object in resolved_objects:
            finalized_objects.extend(
                self.behavior_registry.finalize_resolved_object(
                    resolved_object,
                    visual_profile_catalog,
                )
            )
        instructions = self.primitive_expander(
            tuple(finalized_objects),
            visual_profile_catalog,
        )
        ordered_instructions = tuple(
            sorted(
                instructions,
                key=lambda instruction: _instruction_sort_key(
                    instruction,
                    visual_profile_catalog,
                ),
            )
        )

        canvas = self._background_canvas(render_layout_profile)
        for instruction in ordered_instructions:
            self._compose_instruction(
                canvas,
                instruction,
                visual_profile_catalog,
            )
        return BaseRenderResult(
            image=canvas,
            resolved_objects=tuple(finalized_objects),
            instructions=ordered_instructions,
        )


def build_v1_base_renderer() -> V1BaseRenderer:
    """Return the current concrete base renderer."""

    return V1BaseRenderer(
        resolver=build_v1_render_resolver(),
        primitive_expander=build_v1_primitive_expander(),
        template_loader=build_cached_render_template_loader(),
        behavior_registry=build_v1_render_behavior_registry(),
    )
