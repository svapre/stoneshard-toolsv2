"""Rasterize glow sections into cropped red-mask PNGs.

The current glow shape is derived from the light-core pixels of the road art:

- straight spans use the center bright pixel of the straight road primitive
- junction turns use the bright pixels of the corner primitive

So the generated glow follows the same inner road geometry rather than a
generic thick brush stroke.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from toolsv2.connection_core_geometry import ordered_core_pixels_for_local_connection
from toolsv2.glow.contracts import GlowLineAssetSpec, GlowLineSpec
from toolsv2.glow.section_builder import ArcKey, GlowSection
from toolsv2.production_visual_catalog import build_v1_production_visual_profile_catalog
from toolsv2.render_template_loader import RenderTemplateLoader, build_cached_render_template_loader
from toolsv2.solver_common import Junction, PortId, PortRef
from toolsv2.visual_profiles import DEFAULT_PLAIN_JUNCTION_PROFILE_KEY, VisualProfileCatalog


_RED_MIN = 5
_RED_MAX = 250
_PADDING = 2

_NORTH = PortId("north")
_SOUTH = PortId("south")
_WEST = PortId("west")
_EAST = PortId("east")


def _port_ref_sort_key(port_ref: PortRef):
    if isinstance(port_ref.owner_ref, Junction):
        return (
            "junction",
            f"{port_ref.owner_ref.x_rail_id}|{port_ref.owner_ref.y_rail_id}",
            str(port_ref.owner_local_key),
        )
    return ("node", str(port_ref.owner_ref), str(port_ref.owner_local_key))


def _root_anchor_for_section(
    section: GlowSection,
    *,
    port_pixels_by_port_ref: dict[PortRef, tuple[int, int]],
) -> tuple[int, int] | None:
    if len(section.root_port_refs) != 1:
        return None
    return port_pixels_by_port_ref.get(section.root_port_refs[0])


def _axis_aligned_pixels(
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[tuple[int, int]]:
    x0, y0 = start
    x1, y1 = end
    if x0 == x1:
        step = 1 if y1 >= y0 else -1
        return [(x0, y) for y in range(y0, y1 + step, step)]
    if y0 == y1:
        step = 1 if x1 >= x0 else -1
        return [(x, y0) for x in range(x0, x1 + step, step)]
    raise ValueError("Glow rasterizer only supports axis-aligned segments")


def _arc_pixels(
    arc_key: ArcKey,
    *,
    port_pixels_by_port_ref: dict[PortRef, tuple[int, int]],
    visual_profile_catalog: VisualProfileCatalog,
    template_loader: RenderTemplateLoader,
) -> tuple[tuple[int, int], ...]:
    from_port_ref, to_port_ref = arc_key
    if from_port_ref.owner_ref == to_port_ref.owner_ref and isinstance(from_port_ref.owner_ref, Junction):
        owner_ref = from_port_ref.owner_ref
        return ordered_core_pixels_for_local_connection(
            profile_key=DEFAULT_PLAIN_JUNCTION_PROFILE_KEY,
            from_port_id=PortId(str(from_port_ref.owner_local_key)),
            to_port_id=PortId(str(to_port_ref.owner_local_key)),
            port_pixels_by_port_id={
                _NORTH: port_pixels_by_port_ref[PortRef(owner_ref=owner_ref, owner_local_key=_NORTH)],
                _SOUTH: port_pixels_by_port_ref[PortRef(owner_ref=owner_ref, owner_local_key=_SOUTH)],
                _WEST: port_pixels_by_port_ref[PortRef(owner_ref=owner_ref, owner_local_key=_WEST)],
                _EAST: port_pixels_by_port_ref[PortRef(owner_ref=owner_ref, owner_local_key=_EAST)],
            },
            visual_profile_catalog=visual_profile_catalog,
            template_loader=template_loader,
        )
    start = port_pixels_by_port_ref[from_port_ref]
    end = port_pixels_by_port_ref[to_port_ref]
    return tuple(_axis_aligned_pixels(start, end))


def _component_distances(
    section: GlowSection,
    *,
    port_pixels_by_port_ref: dict[PortRef, tuple[int, int]],
    visual_profile_catalog: VisualProfileCatalog,
    template_loader: RenderTemplateLoader,
) -> tuple[dict[PortRef, int], int]:
    adjacency: dict[PortRef, list[tuple[PortRef, int]]] = {}
    for arc_key in section.arc_keys:
        arc_pixels = _arc_pixels(
            arc_key,
            port_pixels_by_port_ref=port_pixels_by_port_ref,
            visual_profile_catalog=visual_profile_catalog,
            template_loader=template_loader,
        )
        adjacency.setdefault(arc_key[0], []).append((arc_key[1], max(len(arc_pixels) - 1, 1)))

    distances: dict[PortRef, int] = {root: 0 for root in section.root_port_refs}
    queue = deque(section.root_port_refs)
    while queue:
        current = queue.popleft()
        for next_port_ref, arc_length in adjacency.get(current, ()):
            candidate = distances[current] + arc_length
            previous = distances.get(next_port_ref)
            if previous is None or candidate < previous:
                distances[next_port_ref] = candidate
                queue.append(next_port_ref)
    max_distance = max((distances.get(leaf, 0) for leaf in section.leaf_port_refs), default=0)
    return distances, max(max_distance, 1)


@dataclass(frozen=True, slots=True)
class GlowRasterizedLine:
    """One rasterized glow line plus the manifest specs that reference it."""

    image: Image.Image
    asset_spec: GlowLineAssetSpec
    line_spec: GlowLineSpec


def rasterize_glow_section(
    section: GlowSection,
    *,
    asset_name: str,
    port_pixels_by_port_ref: dict[PortRef, tuple[int, int]],
    visual_profile_catalog: VisualProfileCatalog | None = None,
    template_loader: RenderTemplateLoader | None = None,
) -> GlowRasterizedLine:
    """Rasterize one section into a cropped red-mask image and manifest specs."""

    if visual_profile_catalog is None:
        visual_profile_catalog = build_v1_production_visual_profile_catalog()
    if template_loader is None:
        template_loader = build_cached_render_template_loader()

    all_pixels: list[tuple[int, int]] = []
    pixels_by_arc: dict[ArcKey, tuple[tuple[int, int], ...]] = {}
    for arc_key in sorted(
        section.arc_keys,
        key=lambda item: (_port_ref_sort_key(item[0]), _port_ref_sort_key(item[1])),
    ):
        arc_pixels = _arc_pixels(
            arc_key,
            port_pixels_by_port_ref=port_pixels_by_port_ref,
            visual_profile_catalog=visual_profile_catalog,
            template_loader=template_loader,
        )
        pixels_by_arc[arc_key] = arc_pixels
        all_pixels.extend(arc_pixels)
    if not all_pixels:
        raise ValueError(f"Glow section {section.section_id!r} has no drawable geometry")

    min_x = min(x for x, _ in all_pixels) - _PADDING
    max_x = max(x for x, _ in all_pixels) + _PADDING
    min_y = min(y for _, y in all_pixels) - _PADDING
    max_y = max(y for _, y in all_pixels) + _PADDING
    width = max_x - min_x + 1
    height = max_y - min_y + 1

    red_values = Image.new("L", (width, height), 0)
    alpha_values = Image.new("L", (width, height), 0)
    red_pixels = red_values.load()
    alpha_pixels = alpha_values.load()

    port_distances, max_distance = _component_distances(
        section,
        port_pixels_by_port_ref=port_pixels_by_port_ref,
        visual_profile_catalog=visual_profile_catalog,
        template_loader=template_loader,
    )

    def _stamp_pixel(x: int, y: int, red_value: int) -> None:
        local_x = x - min_x
        local_y = y - min_y
        if not (0 <= local_x < width and 0 <= local_y < height):
            return
        alpha_pixels[local_x, local_y] = 255
        red_pixels[local_x, local_y] = max(red_pixels[local_x, local_y], red_value)

    for arc_key, arc_pixels in pixels_by_arc.items():
        start_distance = port_distances.get(arc_key[0], 0)
        arc_length = max(len(arc_pixels) - 1, 1)
        for index, (pixel_x, pixel_y) in enumerate(arc_pixels):
            interpolated_distance = start_distance + round((arc_length * index) / max(len(arc_pixels) - 1, 1))
            normalized = min(1.0, max(0.0, interpolated_distance / max_distance))
            red_value = int(round(_RED_MIN + (_RED_MAX - _RED_MIN) * normalized))
            _stamp_pixel(pixel_x, pixel_y, red_value)

    rgba = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rgba_pixels = rgba.load()
    for y in range(height):
        for x in range(width):
            alpha = alpha_pixels[x, y]
            if alpha == 0:
                continue
            rgba_pixels[x, y] = (red_pixels[x, y], 0, 0, alpha)

    anchor = _root_anchor_for_section(section, port_pixels_by_port_ref=port_pixels_by_port_ref)
    if anchor is None:
        anchor_x = min_x
        anchor_y = min_y
    else:
        anchor_x, anchor_y = anchor
    origin_x = anchor_x - min_x
    origin_y = anchor_y - min_y

    asset_spec = GlowLineAssetSpec(
        asset_id=section.section_id,
        asset_name=asset_name,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    line_spec = GlowLineSpec(
        line_id=section.section_id,
        asset_id=asset_spec.asset_id,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        draw_knot=section.draw_knot,
        point_dependency_groups=section.activation_groups,
        line_dependency_groups=section.line_dependency_groups,
    )
    return GlowRasterizedLine(
        image=rgba,
        asset_spec=asset_spec,
        line_spec=line_spec,
    )


def write_rasterized_glow_line(
    rasterized_line: GlowRasterizedLine,
    out_path: str | Path,
) -> Path:
    """Write one rasterized glow line PNG to disk."""

    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rasterized_line.image.save(output_path)
    return output_path
