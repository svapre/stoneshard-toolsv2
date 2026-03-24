"""Cached render-template loading and transform application."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image

from toolsv2.visual_profiles import (
    RenderTemplateKey,
    RenderTemplateSpec,
    RenderTransformSpec,
)


@dataclass(frozen=True, slots=True)
class LoadedRenderTemplate:
    """One loaded and transformed render template."""

    template_key: RenderTemplateKey
    kind: str
    width: int
    height: int
    image: Image.Image | None = None
    pixel_rows: tuple[tuple[int, ...], ...] = ()


class RenderTemplateLoader(Protocol):
    """Load and cache transformed render templates."""

    def load(
        self,
        template_spec: RenderTemplateSpec,
        transform: RenderTransformSpec = RenderTransformSpec(),
    ) -> LoadedRenderTemplate:
        """Return one loaded transformed template."""

    def load_asset_rgba(self, asset_ref: str) -> Image.Image:
        """Return one loaded RGBA asset image."""


def _rotate_clockwise_rows(
    rows: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    return tuple(
        tuple(rows[len(rows) - 1 - row_index][column_index] for row_index in range(len(rows)))
        for column_index in range(len(rows[0]))
    )


def _apply_transform_to_rows(
    rows: tuple[tuple[int, ...], ...],
    transform: RenderTransformSpec,
) -> tuple[tuple[int, ...], ...]:
    transformed = rows
    if transform.mirror_x:
        transformed = tuple(tuple(reversed(row)) for row in transformed)
    if transform.mirror_y:
        transformed = tuple(reversed(transformed))
    for _ in range(transform.quarter_turns_clockwise):
        transformed = _rotate_clockwise_rows(transformed)
    return transformed


def _apply_transform_to_image(
    image: Image.Image,
    transform: RenderTransformSpec,
) -> Image.Image:
    transformed = image
    if transform.mirror_x:
        transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if transform.mirror_y:
        transformed = transformed.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    for _ in range(transform.quarter_turns_clockwise):
        transformed = transformed.transpose(Image.Transpose.ROTATE_270)
    return transformed


@dataclass(slots=True)
class CachedRenderTemplateLoader:
    """Load and cache transformed render templates from repo-relative assets."""

    project_root: Path | None = None
    _asset_cache: dict[str, Image.Image] = field(init=False, repr=False)
    _template_cache: dict[tuple[str, int, bool, bool], LoadedRenderTemplate] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.project_root is None:
            self.project_root = Path(__file__).resolve().parent
        self._asset_cache: dict[str, Image.Image] = {}
        self._template_cache: dict[tuple[str, int, bool, bool], LoadedRenderTemplate] = {}

    def load_asset_rgba(self, asset_ref: str) -> Image.Image:
        if asset_ref not in self._asset_cache:
            asset_path = Path(self.project_root) / asset_ref
            self._asset_cache[asset_ref] = Image.open(asset_path).convert("RGBA")
        return self._asset_cache[asset_ref]

    def load(
        self,
        template_spec: RenderTemplateSpec,
        transform: RenderTransformSpec = RenderTransformSpec(),
    ) -> LoadedRenderTemplate:
        cache_key = (
            str(template_spec.template_key),
            transform.quarter_turns_clockwise,
            transform.mirror_x,
            transform.mirror_y,
        )
        cached = self._template_cache.get(cache_key)
        if cached is not None:
            return cached

        if template_spec.kind == "sprite_ref":
            assert template_spec.asset_ref is not None
            image = _apply_transform_to_image(
                self.load_asset_rgba(template_spec.asset_ref),
                transform,
            )
            loaded = LoadedRenderTemplate(
                template_key=template_spec.template_key,
                kind=template_spec.kind,
                width=image.width,
                height=image.height,
                image=image,
            )
        else:
            pixel_rows = _apply_transform_to_rows(template_spec.pixel_rows, transform)
            loaded = LoadedRenderTemplate(
                template_key=template_spec.template_key,
                kind=template_spec.kind,
                width=len(pixel_rows[0]),
                height=len(pixel_rows),
                pixel_rows=pixel_rows,
            )
        self._template_cache[cache_key] = loaded
        return loaded


def build_cached_render_template_loader() -> RenderTemplateLoader:
    """Return the default cached template loader."""

    return CachedRenderTemplateLoader()
