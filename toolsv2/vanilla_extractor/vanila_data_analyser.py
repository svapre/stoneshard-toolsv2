from __future__ import annotations

import argparse
import csv
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR / "input"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


@dataclass(frozen=True)
class Match:
    branch_file: str
    kind: str
    top_left_x: int
    top_left_y: int
    center_x: float
    center_y: float
    width: int
    height: int
    right: int
    bottom: int
    score: int


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def read_matches_csv(path: Path) -> list[Match]:
    rows: list[Match] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                Match(
                    branch_file=row["branch_file"],
                    kind=row["kind"],
                    top_left_x=int(row["top_left_x"]),
                    top_left_y=int(row["top_left_y"]),
                    center_x=float(row["center_x"]),
                    center_y=float(row["center_y"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                    right=int(row["right"]),
                    bottom=int(row["bottom"]),
                    score=int(row["score"]),
                )
            )
    return rows


def make_transparent_canvas(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def draw_vertical_grid(
    size: tuple[int, int],
    xs: Iterable[float],
    color: tuple[int, int, int, int],
    *,
    dashed: bool = False,
    dash_len: int = 4,
    gap_len: int = 4,
) -> Image.Image:
    img = make_transparent_canvas(size)
    d = ImageDraw.Draw(img)
    w, h = size
    for x in xs:
        xi = int(round(x))
        if dashed:
            y = 0
            while y < h:
                d.line([(xi, y), (xi, min(y + dash_len, h - 1))], fill=color, width=1)
                y += dash_len + gap_len
        else:
            d.line([(xi, 0), (xi, h - 1)], fill=color, width=1)
    return img


def draw_horizontal_grid(
    size: tuple[int, int],
    ys: Iterable[float],
    color: tuple[int, int, int, int],
    *,
    dashed: bool = False,
    dash_len: int = 4,
    gap_len: int = 4,
) -> Image.Image:
    img = make_transparent_canvas(size)
    d = ImageDraw.Draw(img)
    w, h = size
    for y in ys:
        yi = int(round(y))
        if dashed:
            x = 0
            while x < w:
                d.line([(x, yi), (min(x + dash_len, w - 1), yi)], fill=color, width=1)
                x += dash_len + gap_len
        else:
            d.line([(0, yi), (w - 1, yi)], fill=color, width=1)
    return img


def draw_match_boxes(
    size: tuple[int, int],
    matches: list[Match],
    color: tuple[int, int, int, int],
    *,
    center_cross: bool = True,
) -> Image.Image:
    img = make_transparent_canvas(size)
    d = ImageDraw.Draw(img)
    for m in matches:
        x0 = m.top_left_x
        y0 = m.top_left_y
        x1 = x0 + m.width - 1
        y1 = y0 + m.height - 1
        d.rectangle([(x0, y0), (x1, y1)], outline=color, width=1)
        if center_cross:
            cx = int(round(m.center_x))
            cy = int(round(m.center_y))
            d.line([(cx - 2, cy), (cx + 2, cy)], fill=color, width=1)
            d.line([(cx, cy - 2), (cx, cy + 2)], fill=color, width=1)
    return img


def make_contact_sheet(
    branch_paths: list[Path],
    overlay_layers: list[Image.Image],
    *,
    cols: int = 4,
    margin: int = 18,
    label_h: int = 18,
) -> Image.Image:
    if not branch_paths:
        raise ValueError("No branch files for contact sheet")

    first = load_rgba(branch_paths[0])
    w, h = first.size
    rows = math.ceil(len(branch_paths) / cols)
    sheet = Image.new(
        "RGBA",
        (cols * w + (cols + 1) * margin, rows * (h + label_h) + (rows + 1) * margin),
        (24, 24, 32, 255),
    )
    d = ImageDraw.Draw(sheet)

    for idx, p in enumerate(branch_paths):
        branch = load_rgba(p)
        composite = branch.copy()
        for layer in overlay_layers:
            composite = Image.alpha_composite(composite, layer)

        x0 = margin + (idx % cols) * (w + margin)
        y0 = margin + (idx // cols) * (h + label_h + margin)
        sheet.alpha_composite(composite, (x0, y0))
        d.text((x0, y0 + h + 2), p.stem, fill=(235, 235, 235, 255))

    return sheet


def save_ora(
    out_path: Path,
    canvas_size: tuple[int, int],
    layers: list[tuple[str, Image.Image, float, bool]],
) -> None:
    build_root = out_path.parent / "_ora_build"
    data_dir = build_root / "data"
    thumb_dir = build_root / "Thumbnails"
    data_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[str, str, float, bool]] = []

    for idx, (name, img, opacity, visible) in enumerate(layers):
        filename = f"layer_{idx:02d}.png"
        img.save(data_dir / filename)
        entries.append((name, f"data/{filename}", opacity, visible))

    merged = make_transparent_canvas(canvas_size)
    for _name, img, _opacity, visible in layers:
        if visible:
            merged = Image.alpha_composite(merged, img)
    merged.save(build_root / "mergedimage.png")

    thumb = merged.copy()
    thumb.thumbnail((256, 256))
    thumb.save(thumb_dir / "thumbnail.png")

    stack_lines = [
        f'<image version="0.0.3" w="{canvas_size[0]}" h="{canvas_size[1]}">',
        '  <stack name="root">',
    ]
    for name, src, opacity, visible in entries:
        stack_lines.append(
            f'    <layer name="{name}" src="{src}" opacity="{opacity:.3f}" '
            f'visibility="{"visible" if visible else "hidden"}" x="0" y="0" />'
        )
    stack_lines += ["  </stack>", "</image>"]

    (build_root / "stack.xml").write_text("\n".join(stack_lines), encoding="utf-8")
    (build_root / "mimetype").write_text("image/openraster", encoding="utf-8")

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(build_root / "mimetype", arcname="mimetype", compress_type=zipfile.ZIP_STORED)
    with zipfile.ZipFile(out_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(build_root / "stack.xml", arcname="stack.xml")
        zf.write(build_root / "mergedimage.png", arcname="mergedimage.png")
        zf.write(thumb_dir / "thumbnail.png", arcname="Thumbnails/thumbnail.png")
        for idx in range(len(layers)):
            filename = f"layer_{idx:02d}.png"
            zf.write(data_dir / filename, arcname=f"data/{filename}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a GIMP/Krita ORA with extracted x/y grids and matched roads/gates in separate layers."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing vanilla branch PNGs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder containing grid_report.json and matches CSVs, and where outputs will be written",
    )
    parser.add_argument(
        "--background",
        type=Path,
        default=SCRIPT_DIR.parent / "art/source/background/base/BASE_BACKGROUND.png",
        help="Path to BASE_BACKGROUND.png",
    )
    parser.add_argument(
        "--grid-report",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "grid_report.json",
        help="Path to grid_report.json",
    )
    parser.add_argument(
        "--frame-matches",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "frame_matches.csv",
        help="Path to frame_matches.csv",
    )
    parser.add_argument(
        "--gate-matches",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "gate_matches.csv",
        help="Path to gate_matches.csv",
    )
    parser.add_argument(
        "--road-matches",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "road_tb_matches.csv",
        help="Path to road_tb_matches.csv",
    )
    parser.add_argument(
        "--branch-glob",
        default="s_*_branch_0.png",
        help="Glob for branch PNGs inside input dir",
    )
    parser.add_argument(
        "--ora-name",
        default="vanilla_extracted_grid.ora",
        help="Output ORA filename",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    background = load_rgba(args.background)
    canvas_size = background.size

    with args.grid_report.open("r", encoding="utf-8") as f:
        report = json.load(f)

    stats = report["stats"]
    major_x = stats.get("major_frame_center_x_rails", [])
    midpoint_x = stats.get("midpoint_x_candidates", [])
    major_y = stats.get("major_frame_center_y_rails", [])
    midpoint_y = stats.get("midpoint_y_candidates", [])

    frame_matches = read_matches_csv(args.frame_matches) if args.frame_matches.exists() else []
    gate_matches = read_matches_csv(args.gate_matches) if args.gate_matches.exists() else []
    road_matches = read_matches_csv(args.road_matches) if args.road_matches.exists() else []

    branch_paths = sorted(p for p in args.input_dir.glob(args.branch_glob) if p.is_file())

    # Separate branch layers, initially hidden except the first one.
    branch_layers: list[tuple[str, Image.Image, float, bool]] = []
    for idx, branch_path in enumerate(branch_paths):
        branch_img = load_rgba(branch_path)
        if branch_img.size != canvas_size:
            continue
        branch_layers.append((f"branch::{branch_path.stem}", branch_img, 0.55, idx == 0))

    # Grid layers separated by axis and type.
    major_x_layer = draw_vertical_grid(canvas_size, major_x, (255, 64, 64, 150), dashed=False)
    midpoint_x_layer = draw_vertical_grid(canvas_size, midpoint_x, (255, 180, 0, 120), dashed=True)
    major_y_layer = draw_horizontal_grid(canvas_size, major_y, (64, 255, 96, 150), dashed=False)
    midpoint_y_layer = draw_horizontal_grid(canvas_size, midpoint_y, (0, 220, 255, 110), dashed=True)

    # Data overlays separated by primitive type.
    frame_boxes = draw_match_boxes(canvas_size, frame_matches, (255, 255, 255, 100))
    gate_boxes = draw_match_boxes(canvas_size, gate_matches, (255, 0, 255, 150))
    road_boxes = draw_match_boxes(canvas_size, road_matches, (0, 180, 255, 120))

    layers: list[tuple[str, Image.Image, float, bool]] = [
        ("background::BASE_BACKGROUND", background, 0.45, True),
        ("grid::major_x", major_x_layer, 1.0, True),
        ("grid::midpoint_x", midpoint_x_layer, 1.0, True),
        ("grid::major_y", major_y_layer, 1.0, True),
        ("grid::midpoint_y", midpoint_y_layer, 1.0, False),
        ("matches::frame_boxes", frame_boxes, 1.0, False),
        ("matches::gate_boxes", gate_boxes, 1.0, True),
        ("matches::road_tb_boxes", road_boxes, 1.0, False),
    ]
    layers.extend(branch_layers)

    ora_path = output_dir / args.ora_name
    save_ora(ora_path, canvas_size, layers)

    # Also make a contact sheet for quick viewing.
    contact_overlay_layers = [major_x_layer, midpoint_x_layer, major_y_layer, gate_boxes]
    if branch_paths:
        contact_sheet = make_contact_sheet(branch_paths, contact_overlay_layers)
        contact_sheet.save(output_dir / "grid_contact_sheet_extracted.png")

    print(f"Created ORA: {ora_path}")
    if branch_paths:
        print(f"Created contact sheet: {output_dir / 'grid_contact_sheet_extracted.png'}")
    print("Used extracted data from:")
    print(f"  {args.grid_report}")
    print(f"  {args.frame_matches}")
    print(f"  {args.gate_matches}")
    print(f"  {args.road_matches}")


if __name__ == "__main__":
    main()
