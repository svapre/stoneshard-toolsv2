from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR / "input"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


@dataclass(frozen=True)
class Match:
    branch_file: str
    kind: str
    x: int
    y: int
    w: int
    h: int
    score: int

    @property
    def center_x(self) -> float:
        return self.x + (self.w - 1) / 2.0

    @property
    def center_y(self) -> float:
        return self.y + (self.h - 1) / 2.0

    @property
    def right(self) -> int:
        return self.x + self.w - 1

    @property
    def bottom(self) -> int:
        return self.y + self.h - 1


@dataclass(frozen=True)
class PrimitiveInfo:
    name: str
    filename: str
    crop_offset_x: int
    crop_offset_y: int
    crop_w: int
    crop_h: int
    opaque_pixel_count: int


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def alpha_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError(f"{img=} has no non-transparent pixels")
    return bbox


def crop_to_alpha(img: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    bbox = alpha_bbox(img)
    cropped = img.crop(bbox)
    return cropped, (bbox[0], bbox[1])


def count_opaque_pixels(img: Image.Image) -> int:
    px = img.load()
    count = 0
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] > 0:
                count += 1
    return count


def iter_candidate_positions(
    haystack_w: int,
    haystack_h: int,
    needle_w: int,
    needle_h: int,
) -> Iterable[tuple[int, int]]:
    max_x = haystack_w - needle_w
    max_y = haystack_h - needle_h
    for y in range(max_y + 1):
        for x in range(max_x + 1):
            yield x, y


def exact_alpha_match(
    haystack: Image.Image,
    needle: Image.Image,
    x: int,
    y: int,
    *,
    require_transparent_outside: bool = False,
) -> bool:
    hpx = haystack.load()
    npx = needle.load()
    for ny in range(needle.height):
        for nx in range(needle.width):
            nr, ng, nb, na = npx[nx, ny]
            hr, hg, hb, ha = hpx[x + nx, y + ny]
            if na > 0:
                if (hr, hg, hb, ha) != (nr, ng, nb, na):
                    return False
            elif require_transparent_outside and ha != 0:
                return False
    return True


def bg_subtracted_match_score(
    branch: Image.Image,
    background: Image.Image,
    needle: Image.Image,
    x: int,
    y: int,
) -> int:
    bpx = branch.load()
    npx = needle.load()
    _bgpx = background.load()
    score = 0
    for ny in range(needle.height):
        for nx in range(needle.width):
            nr, ng, nb, na = npx[nx, ny]
            if na == 0:
                continue
            br, bg, bb, ba = bpx[x + nx, y + ny]
            if (br, bg, bb, ba) == (nr, ng, nb, na):
                score += 1
    return score


def find_exact_matches(
    branch_name: str,
    branch: Image.Image,
    background: Image.Image,
    primitive: Image.Image,
    kind: str,
    *,
    require_transparent_outside: bool = False,
) -> list[Match]:
    matches: list[Match] = []
    for x, y in iter_candidate_positions(branch.width, branch.height, primitive.width, primitive.height):
        if exact_alpha_match(
            branch,
            primitive,
            x,
            y,
            require_transparent_outside=require_transparent_outside,
        ):
            score = bg_subtracted_match_score(branch, background, primitive, x, y)
            matches.append(Match(branch_name, kind, x, y, primitive.width, primitive.height, score))
    return matches


def suppress_overlaps(matches: list[Match], iou_threshold: float = 0.2) -> list[Match]:
    def iou(a: Match, b: Match) -> float:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        union = a.w * a.h + b.w * b.h - inter
        return inter / union

    kept: list[Match] = []
    for m in sorted(matches, key=lambda z: (-z.score, z.branch_file, z.y, z.x)):
        if all(iou(m, k) <= iou_threshold for k in kept):
            kept.append(m)
    return sorted(kept, key=lambda z: (z.branch_file, z.y, z.x, z.kind))


def summarize_int_positions(values: list[float]) -> dict[str, object]:
    rounded = [int(round(v)) for v in values]
    counts = Counter(rounded)
    uniq = sorted(counts)
    diffs = [b - a for a, b in zip(uniq, uniq[1:])]
    diff_counts = Counter(diffs)
    return {
        "unique_positions": uniq,
        "position_counts": dict(sorted(counts.items())),
        "diff_counts": dict(sorted(diff_counts.items())),
    }


def nearest_grid_step(values: list[int]) -> int | None:
    if len(values) < 2:
        return None
    diffs = [b - a for a, b in zip(sorted(values), sorted(values)[1:]) if b > a]
    if not diffs:
        return None
    return Counter(diffs).most_common(1)[0][0]


def compute_row_patterns(frame_matches: list[Match]) -> dict[str, list[list[int]]]:
    by_branch_and_y: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for m in frame_matches:
        y = int(round(m.center_y))
        x = int(round(m.center_x))
        by_branch_and_y[m.branch_file][y].append(x)

    patterns: dict[str, Counter[tuple[int, ...]]] = defaultdict(Counter)
    for _branch, y_map in by_branch_and_y.items():
        for _y, xs in y_map.items():
            xs_sorted = sorted(xs)
            patterns[str(len(xs_sorted))][tuple(xs_sorted)] += 1

    return {
        row_count: [list(pattern) for pattern, _count in counter.most_common()]
        for row_count, counter in sorted(patterns.items(), key=lambda kv: int(kv[0]))
    }


def compute_midpoints(values: list[int]) -> list[float]:
    uniq = sorted(set(values))
    mids: list[float] = []
    for a, b in zip(uniq, uniq[1:]):
        mids.append((a + b) / 2.0)
    return mids


def collect_useful_stats(
    frame_matches: list[Match],
    gate_matches: list[Match],
    road_matches: list[Match],
) -> dict[str, object]:
    frame_x = [m.center_x for m in frame_matches]
    frame_y = [m.center_y for m in frame_matches]
    gate_x = [m.center_x for m in gate_matches]
    gate_y = [m.center_y for m in gate_matches]
    road_x = [m.center_x for m in road_matches]
    road_y = [m.center_y for m in road_matches]

    frame_x_summary = summarize_int_positions(frame_x)
    frame_y_summary = summarize_int_positions(frame_y)
    gate_x_summary = summarize_int_positions(gate_x) if gate_x else {}
    gate_y_summary = summarize_int_positions(gate_y) if gate_y else {}
    road_x_summary = summarize_int_positions(road_x) if road_x else {}
    road_y_summary = summarize_int_positions(road_y) if road_y else {}

    major_x = frame_x_summary["unique_positions"]
    major_y = frame_y_summary["unique_positions"]
    midpoint_x = compute_midpoints(major_x)
    midpoint_y = compute_midpoints(major_y)

    return {
        "frame_x_summary": frame_x_summary,
        "frame_y_summary": frame_y_summary,
        "gate_x_summary": gate_x_summary,
        "gate_y_summary": gate_y_summary,
        "road_x_summary": road_x_summary,
        "road_y_summary": road_y_summary,
        "major_frame_center_x_rails": major_x,
        "major_frame_center_y_rails": major_y,
        "midpoint_x_candidates": midpoint_x,
        "midpoint_y_candidates": midpoint_y,
        "dominant_frame_x_step": nearest_grid_step(major_x),
        "dominant_frame_y_step": nearest_grid_step(major_y),
        "row_patterns_by_skill_count": compute_row_patterns(frame_matches),
    }


def write_matches_csv(path: Path, matches: list[Match]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "branch_file",
                "kind",
                "top_left_x",
                "top_left_y",
                "center_x",
                "center_y",
                "width",
                "height",
                "right",
                "bottom",
                "score",
            ]
        )
        for m in matches:
            writer.writerow(
                [
                    m.branch_file,
                    m.kind,
                    m.x,
                    m.y,
                    f"{m.center_x:.1f}",
                    f"{m.center_y:.1f}",
                    m.w,
                    m.h,
                    m.right,
                    m.bottom,
                    m.score,
                ]
            )


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def print_summary(
    primitive_infos: list[PrimitiveInfo],
    frame_matches: list[Match],
    gate_matches: list[Match],
    road_matches: list[Match],
    stats: dict[str, object],
) -> None:
    print("Primitive alpha crops:")
    for info in primitive_infos:
        print(
            f"  {info.name:8s} "
            f"file={info.filename} "
            f"crop_offset=({info.crop_offset_x},{info.crop_offset_y}) "
            f"crop_size=({info.crop_w}x{info.crop_h}) "
            f"opaque_pixels={info.opaque_pixel_count}"
        )

    by_branch: dict[str, Counter[str]] = defaultdict(Counter)
    for m in frame_matches + gate_matches + road_matches:
        by_branch[m.branch_file][m.kind] += 1

    print("\nPer-branch primitive counts:")
    for branch_name in sorted(by_branch):
        counts = by_branch[branch_name]
        print(
            f"  {branch_name}: "
            f"frames={counts.get('frame', 0)}, "
            f"gates={counts.get('gate', 0)}, "
            f"road_tb={counts.get('road_tb', 0)}"
        )

    print("\nFrame center X rails:", stats["major_frame_center_x_rails"])
    print("Frame center Y rails:", stats["major_frame_center_y_rails"])
    print("Frame midpoint X candidates:", stats["midpoint_x_candidates"])
    print("Frame midpoint Y candidates:", stats["midpoint_y_candidates"])
    print("Dominant frame X step:", stats["dominant_frame_x_step"])
    print("Dominant frame Y step:", stats["dominant_frame_y_step"])

    print("\nCommon row patterns by skill count:")
    row_patterns = stats["row_patterns_by_skill_count"]
    for row_count, patterns in row_patterns.items():
        print(f"  {row_count} skills:")
        for pattern in patterns[:10]:
            print(f"    {pattern}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scan all PNG files in ./input, match vanilla primitives, and extract "
            "reusable grid/pattern data."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing all vanilla branch PNGs plus primitive PNGs if desired.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder to write CSV/JSON reports.",
    )
    parser.add_argument(
        "--background",
        type=Path,
        default=SCRIPT_DIR.parent / "art/source/background/base/BASE_BACKGROUND.png",
        help="Path to BASE_BACKGROUND.png",
    )
    parser.add_argument(
        "--frame",
        type=Path,
        default=SCRIPT_DIR.parent / "art/source/node/skill_frame/FRAME_ROOT.png",
        help="Path to FRAME_ROOT.png",
    )
    parser.add_argument(
        "--gate",
        type=Path,
        default=SCRIPT_DIR.parent / "art/source/node/and_knot/GATE_AND.png",
        help="Path to GATE_AND.png",
    )
    parser.add_argument(
        "--road",
        type=Path,
        default=SCRIPT_DIR.parent / "art/source/connection/external_straight/NONDIR_PORTS_TB.png",
        help="Path to NONDIR_PORTS_TB.png",
    )
    parser.add_argument(
        "--strict-transparent",
        action="store_true",
        help="Require transparent primitive pixels to also match transparent destination pixels.",
    )
    parser.add_argument(
        "--branch-glob",
        default="*.png",
        help="Glob for branch images inside input dir. Primitive files are auto-excluded by name.",
    )
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    background = load_rgba(args.background)
    frame = load_rgba(args.frame)
    gate = load_rgba(args.gate)
    road = load_rgba(args.road)

    frame_cropped, frame_offset = crop_to_alpha(frame)
    gate_cropped, gate_offset = crop_to_alpha(gate)
    road_cropped, road_offset = crop_to_alpha(road)

    primitive_infos = [
        PrimitiveInfo(
            "frame",
            Path(args.frame).name,
            frame_offset[0],
            frame_offset[1],
            frame_cropped.width,
            frame_cropped.height,
            count_opaque_pixels(frame_cropped),
        ),
        PrimitiveInfo(
            "gate",
            Path(args.gate).name,
            gate_offset[0],
            gate_offset[1],
            gate_cropped.width,
            gate_cropped.height,
            count_opaque_pixels(gate_cropped),
        ),
        PrimitiveInfo(
            "road_tb",
            Path(args.road).name,
            road_offset[0],
            road_offset[1],
            road_cropped.width,
            road_cropped.height,
            count_opaque_pixels(road_cropped),
        ),
    ]

    excluded_names = {
        Path(args.background).name,
        Path(args.frame).name,
        Path(args.gate).name,
        Path(args.road).name,
    }

    branch_paths = [
        p for p in sorted(input_dir.glob(args.branch_glob))
        if p.is_file() and p.name not in excluded_names
    ]
    if not branch_paths:
        raise FileNotFoundError(
            f"No branch PNGs found in {input_dir} with glob {args.branch_glob}"
        )

    frame_matches: list[Match] = []
    gate_matches: list[Match] = []
    road_matches: list[Match] = []

    for branch_path in branch_paths:
        branch = load_rgba(branch_path)
        if branch.size != background.size:
            print(f"Skipping {branch_path.name}: size {branch.size} != background size {background.size}")
            continue

        f_matches = suppress_overlaps(
            find_exact_matches(
                branch_path.name,
                branch,
                background,
                frame_cropped,
                "frame",
                require_transparent_outside=args.strict_transparent,
            )
        )
        g_matches = suppress_overlaps(
            find_exact_matches(
                branch_path.name,
                branch,
                background,
                gate_cropped,
                "gate",
                require_transparent_outside=args.strict_transparent,
            )
        )
        r_matches = suppress_overlaps(
            find_exact_matches(
                branch_path.name,
                branch,
                background,
                road_cropped,
                "road_tb",
                require_transparent_outside=args.strict_transparent,
            )
        )

        frame_matches.extend(f_matches)
        gate_matches.extend(g_matches)
        road_matches.extend(r_matches)

    stats = collect_useful_stats(frame_matches, gate_matches, road_matches)

    output_dir.mkdir(parents=True, exist_ok=True)

    write_matches_csv(output_dir / "frame_matches.csv", frame_matches)
    write_matches_csv(output_dir / "gate_matches.csv", gate_matches)
    write_matches_csv(output_dir / "road_tb_matches.csv", road_matches)

    all_matches = sorted(frame_matches + gate_matches + road_matches, key=lambda m: (m.branch_file, m.kind, m.y, m.x))
    write_matches_csv(output_dir / "all_matches.csv", all_matches)

    json_report = {
        "primitive_infos": [asdict(p) for p in primitive_infos],
        "branch_count": len({m.branch_file for m in all_matches}),
        "match_counts": {
            "frame": len(frame_matches),
            "gate": len(gate_matches),
            "road_tb": len(road_matches),
            "all": len(all_matches),
        },
        "stats": stats,
    }
    write_json(output_dir / "grid_report.json", json_report)

    print_summary(primitive_infos, frame_matches, gate_matches, road_matches, stats)
    print(f"\nWrote reports to: {output_dir}")


if __name__ == "__main__":
    main()
