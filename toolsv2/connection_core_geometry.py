"""Shared connection-core geometry derived from render profile bindings.

This module is the single source of truth for the current inner road-core
geometry that both the road renderer and the glow exporter should follow.
It intentionally reuses the same local-connection binding and local-block
placement rules as the render finalizer, so changing the junction piece
binding/template does not require a separate glow-side rewrite.
"""

from __future__ import annotations

from toolsv2.render_template_loader import LoadedRenderTemplate, RenderTemplateLoader
from toolsv2.solver_common import PortId, RenderProfileKey
from toolsv2.visual_profiles import (
    BuildGeometryProfile,
    RenderStyleProfile,
    RenderTemplateBinding,
    VisualProfileCatalog,
)


def local_connection_binding(
    style_profile: RenderStyleProfile,
    *,
    from_port_id: PortId,
    to_port_id: PortId,
) -> RenderTemplateBinding:
    expected_pair = frozenset((from_port_id, to_port_id))
    for local_connection_template in style_profile.local_connection_templates:
        if frozenset(local_connection_template.port_ids) == expected_pair:
            return local_connection_template.binding
    raise KeyError(
        f"No local connection template binding is frozen for port pair {tuple(sorted(str(port_id) for port_id in expected_pair))}"
    )


def repeated_local_top_left_positions(
    *,
    local_start_x: int,
    local_start_y: int,
    local_end_x: int,
    local_end_y: int,
    template: LoadedRenderTemplate,
    binding: RenderTemplateBinding,
) -> tuple[tuple[int, int], ...] | None:
    if local_start_y == local_end_y:
        center_y = local_start_y + binding.offset_y
        min_center_x = min(local_start_x, local_end_x)
        max_center_x = max(local_start_x, local_end_x)
        return tuple(
            (
                center_x + binding.offset_x - (template.width // 2),
                center_y - (template.height // 2),
            )
            for center_x in range(min_center_x, max_center_x + 1)
        )
    if local_start_x == local_end_x:
        center_x = local_start_x + binding.offset_x
        min_center_y = min(local_start_y, local_end_y)
        max_center_y = max(local_start_y, local_end_y)
        return tuple(
            (
                center_x - (template.width // 2),
                center_y + binding.offset_y - (template.height // 2),
            )
            for center_y in range(min_center_y, max_center_y + 1)
        )
    return None


def centered_local_top_left(
    *,
    local_canvas_width: int,
    local_canvas_height: int,
    template: LoadedRenderTemplate,
    binding: RenderTemplateBinding,
) -> tuple[int, int]:
    return (
        (local_canvas_width // 2) + binding.offset_x - (template.width // 2),
        (local_canvas_height // 2) + binding.offset_y - (template.height // 2),
    )


def _orthogonal_neighbors(pixel: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = pixel
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


def brightest_ordered_pixel_path_for_loaded_template(
    template: LoadedRenderTemplate,
) -> tuple[tuple[int, int], ...]:
    if template.kind != "sprite_ref" or template.image is None:
        raise NotImplementedError("Connection core geometry currently supports sprite_ref templates only")

    image = template.image.convert("RGBA")
    max_brightness = None
    pixels: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = image.getpixel((x, y))
            if a == 0:
                continue
            brightness = r + g + b
            if max_brightness is None or brightness > max_brightness:
                max_brightness = brightness
                pixels = [(x, y)]
            elif brightness == max_brightness:
                pixels.append((x, y))
    if not pixels:
        raise ValueError(f"No opaque pixels found in template {template.template_key!r}")

    pixel_set = set(pixels)
    adjacency = {
        pixel: tuple(
            neighbor
            for neighbor in _orthogonal_neighbors(pixel)
            if neighbor in pixel_set
        )
        for pixel in pixels
    }
    endpoints = sorted(
        (pixel for pixel, neighbors in adjacency.items() if len(neighbors) <= 1),
        key=lambda item: (item[1], item[0]),
    )
    start = endpoints[0] if endpoints else min(pixels, key=lambda item: (item[1], item[0]))

    ordered: list[tuple[int, int]] = [start]
    previous: tuple[int, int] | None = None
    current = start
    while True:
        candidates = [neighbor for neighbor in adjacency[current] if neighbor != previous]
        if not candidates:
            break
        next_pixel = sorted(candidates, key=lambda item: (item[1], item[0]))[0]
        ordered.append(next_pixel)
        previous, current = current, next_pixel
    return tuple(ordered)


def _anchor_from_port_pixels(
    build_profile: BuildGeometryProfile,
    port_pixels_by_port_id: dict[PortId, tuple[int, int]],
) -> tuple[int, int]:
    geometry_by_port_id = {port.port_id: port for port in build_profile.ports}
    anchors = {
        (
            pixel_x - geometry_by_port_id[port_id].offset_x,
            pixel_y - geometry_by_port_id[port_id].offset_y,
        )
        for port_id, (pixel_x, pixel_y) in port_pixels_by_port_id.items()
        if port_id in geometry_by_port_id
    }
    if not anchors:
        raise ValueError("Cannot resolve object anchor without any known port geometry positions")
    if len(anchors) != 1:
        raise ValueError(f"Inconsistent port pixels for one object anchor: {sorted(anchors)!r}")
    return next(iter(anchors))


def ordered_core_pixels_for_local_connection(
    *,
    profile_key: RenderProfileKey,
    from_port_id: PortId,
    to_port_id: PortId,
    port_pixels_by_port_id: dict[PortId, tuple[int, int]],
    visual_profile_catalog: VisualProfileCatalog,
    template_loader: RenderTemplateLoader,
) -> tuple[tuple[int, int], ...]:
    build_profile = visual_profile_catalog.build_geometry_profile(profile_key)
    style_profile = visual_profile_catalog.render_style_profile(profile_key)
    if build_profile.footprint.anchor_x != 0 or build_profile.footprint.anchor_y != 0:
        raise NotImplementedError("Connection core geometry requires zero local footprint anchor offsets")

    binding = local_connection_binding(
        style_profile,
        from_port_id=from_port_id,
        to_port_id=to_port_id,
    )
    template_spec = visual_profile_catalog.render_template_spec(binding.template_key)
    loaded_template = template_loader.load(template_spec, binding.transform)
    if loaded_template.kind != "sprite_ref" or loaded_template.image is None:
        raise NotImplementedError("Connection core geometry currently supports sprite_ref templates only")

    anchor_x, anchor_y = _anchor_from_port_pixels(build_profile, port_pixels_by_port_id)
    object_origin_x = anchor_x - (build_profile.footprint.width // 2)
    object_origin_y = anchor_y - (build_profile.footprint.height // 2)
    local_port_positions = {
        port_id: (pixel_x - object_origin_x, pixel_y - object_origin_y)
        for port_id, (pixel_x, pixel_y) in port_pixels_by_port_id.items()
    }

    from_position = local_port_positions[from_port_id]
    to_position = local_port_positions[to_port_id]
    repeated_positions = repeated_local_top_left_positions(
        local_start_x=from_position[0],
        local_start_y=from_position[1],
        local_end_x=to_position[0],
        local_end_y=to_position[1],
        template=loaded_template,
        binding=binding,
    )
    positions = (
        repeated_positions
        if repeated_positions is not None
        else (
            centered_local_top_left(
                local_canvas_width=build_profile.footprint.width,
                local_canvas_height=build_profile.footprint.height,
                template=loaded_template,
                binding=binding,
            ),
        )
    )

    template_core_pixels = brightest_ordered_pixel_path_for_loaded_template(loaded_template)
    ordered_pixels: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for top_left_x, top_left_y in positions:
        for pixel_x, pixel_y in template_core_pixels:
            global_pixel = (
                object_origin_x + top_left_x + pixel_x,
                object_origin_y + top_left_y + pixel_y,
            )
            if global_pixel in seen:
                continue
            seen.add(global_pixel)
            ordered_pixels.append(global_pixel)

    source_pixel = port_pixels_by_port_id[from_port_id]
    if ordered_pixels:
        start_distance = abs(ordered_pixels[0][0] - source_pixel[0]) + abs(ordered_pixels[0][1] - source_pixel[1])
        end_distance = abs(ordered_pixels[-1][0] - source_pixel[0]) + abs(ordered_pixels[-1][1] - source_pixel[1])
        if end_distance < start_distance:
            ordered_pixels.reverse()
    return tuple(ordered_pixels)
