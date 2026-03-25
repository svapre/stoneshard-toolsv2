from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MslEntry:
    section_index: int
    path: str
    offset: int
    size: int


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def parse_msl(data: bytes) -> tuple[list[MslEntry], int]:
    if not data.startswith(b"MSLMv"):
        raise ValueError("Not an MSL package")

    header_end = data.find(b"A")
    if header_end < 0:
        raise ValueError("Could not locate MSL header terminator")
    header_end += 1

    # Current MSL packages in this workspace store the section count as a
    # 3-byte little-endian value immediately after the version tag.
    if header_end + 3 > len(data):
        raise ValueError("Incomplete MSL header")
    section_hint = int.from_bytes(data[header_end : header_end + 3], "little")
    if section_hint <= 0:
        raise ValueError("Invalid section hint in MSL header")

    entries: list[MslEntry] = []
    pos = header_end + 3
    section_index = 0

    while True:
        if pos + 4 > len(data):
            raise ValueError("Unexpected EOF while reading MSL tables")
        name_len = _read_u32(data, pos)
        if name_len == 0:
            pos += 4
            if pos >= len(data):
                raise ValueError("Unexpected EOF after MSL section sentinel")
            if pos + 4 > len(data):
                payload_base = pos
                break
            maybe_count = _read_u32(data, pos)
            if maybe_count == 0:
                payload_base = pos + 4
                break
            next_path_len_offset = pos + 4
            if next_path_len_offset + 4 > len(data):
                raise ValueError("Unexpected EOF after MSL section sentinel")
            next_path_len = _read_u32(data, next_path_len_offset)
            if maybe_count > 100000 or next_path_len == 0 or next_path_len > 4096:
                payload_base = pos
                break
            section_index += 1
            pos += 4
            continue

        if name_len > 4096:
            raise ValueError(f"Suspicious MSL path length {name_len} at offset {pos:#x}")
        name_start = pos + 4
        name_end = name_start + name_len
        if name_end + 8 > len(data):
            raise ValueError("Unexpected EOF while reading MSL entry")
        path = data[name_start:name_end].decode("utf-8")
        offset = _read_u32(data, name_end)
        size = _read_u32(data, name_end + 4)
        entries.append(MslEntry(section_index=section_index, path=path, offset=offset, size=size))
        pos = name_end + 8

    for entry in entries:
        start = payload_base + entry.offset
        end = start + entry.size
        if end > len(data):
            raise ValueError(f"Entry {entry.path} points outside payload")

    return entries, payload_base


def unpack_msl(msl_path: Path, output_dir: Path) -> list[MslEntry]:
    data = msl_path.read_bytes()
    entries, payload_base = parse_msl(data)

    for entry in entries:
        target = output_dir / Path(entry.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        start = payload_base + entry.offset
        end = start + entry.size
        target.write_bytes(data[start:end])

    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Unpack an MSL .sml package")
    parser.add_argument("msl_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    entries = unpack_msl(args.msl_path, args.output_dir)
    print(f"Extracted {len(entries)} files to {args.output_dir}")


if __name__ == "__main__":
    main()
