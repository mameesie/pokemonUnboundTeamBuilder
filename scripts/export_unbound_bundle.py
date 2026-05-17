from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

from extract_unbound_data import (
    OUTPUT_DIR,
    ROM_PATH,
    main as extract_rom_data,
)

BUNDLE_DIR = Path("research/unbound-bundle")
DECODED_DIR = BUNDLE_DIR / "decoded"
RAW_DIR = BUNDLE_DIR / "raw"


def ensure_clean_bundle_dir() -> None:
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    DECODED_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def copy_decoded_outputs() -> list[str]:
    copied: list[str] = []
    for path in sorted(OUTPUT_DIR.glob("*.json")):
        destination = DECODED_DIR / path.name
        shutil.copy2(path, destination)
        copied.append(str(destination))
    return copied


def dump_resource_map(data: bytes) -> None:
    entries = []
    for loc in range(0x128, 0x1D8, 4):
        value = struct.unpack_from("<I", data, loc)[0]
        rom_offset = value - 0x08000000 if 0x08000000 <= value < 0x08000000 + len(data) else None
        entries.append(
            {
                "tableOffset": hex(loc),
                "rawValue": hex(value),
                "romOffset": hex(rom_offset) if rom_offset is not None else None,
            }
        )

    with (RAW_DIR / "resource-map.json").open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)


def dump_pointer_table(data: bytes, table_offset: int, count: int, out_name: str) -> None:
    entries = []
    for index in range(count):
        raw_pointer = struct.unpack_from("<I", data, table_offset + index * 4)[0]
        entries.append(
            {
                "index": index,
                "rawPointer": hex(raw_pointer),
                "romOffset": hex(raw_pointer - 0x08000000),
            }
        )

    with (RAW_DIR / out_name).open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "tableOffset": hex(table_offset),
                "entryCount": count,
                "entries": entries,
            },
            handle,
            indent=2,
        )


def dump_sparse_pair_table(data: bytes, table_offset: int, count: int, out_name: str) -> None:
    entries = []
    for index in range(count):
        raw_pointer = struct.unpack_from("<I", data, table_offset + index * 8)[0]
        numeric_value = struct.unpack_from("<I", data, table_offset + index * 8 + 4)[0]
        entries.append(
            {
                "index": index,
                "rawPointer": hex(raw_pointer),
                "romOffset": hex(raw_pointer - 0x08000000),
                "numericValue": numeric_value,
                "numericValueHex": hex(numeric_value),
            }
        )

    with (RAW_DIR / out_name).open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "tableOffset": hex(table_offset),
                "entryCount": count,
                "entries": entries,
            },
            handle,
            indent=2,
        )


def dump_regions(data: bytes) -> list[str]:
    written: list[str] = []

    regions = {
        "species-name-table.bin": (0x166A997, 0x166A997 + 1293 * 11),
        "base-stats-table.bin": (0x19E0CB8, 0x19E0CB8 + 1293 * 0x1C),
        "move-name-table.bin": (0x0A40A10, 0x0A40A10 + 923 * 13),
        "move-data-table.bin": (0x0A769AF, 0x0A769AF + 923 * 12),
        "ability-name-table.bin": (0x0A36398, 0x0A36398 + 292 * 17),
        "levelup-pointer-table.bin": (0x1A2457C, 0x1A2457C + (1293 + 1) * 4),
        "learnset-sparse-pair-table.bin": (0x1A32BDC, 0x1A32BDC + 413 * 8),
    }

    for file_name, (start, end) in regions.items():
        destination = RAW_DIR / file_name
        destination.write_bytes(data[start:end])
        written.append(str(destination))

    return written


def write_manifest(decoded_files: list[str], raw_region_files: list[str]) -> None:
    manifest = {
        "bundleVersion": 1,
        "romPath": str(ROM_PATH),
        "bundleDir": str(BUNDLE_DIR),
        "decodedFiles": decoded_files,
        "rawFiles": raw_region_files
        + [
            str(RAW_DIR / "resource-map.json"),
            str(RAW_DIR / "levelup-pointer-table.json"),
            str(RAW_DIR / "learnset-sparse-pair-table.json"),
        ],
        "notes": [
            "This bundle contains all currently decoded JSON plus raw candidate tables for unresolved ROM structures.",
            "Level-up learnsets and move battle metadata are already decoded.",
            "Evolutions, egg moves, TM compatibility, and trainer parties are not decoded yet.",
        ],
    }

    with (BUNDLE_DIR / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


def main() -> None:
    extract_rom_data()
    ensure_clean_bundle_dir()

    decoded_files = copy_decoded_outputs()
    data = ROM_PATH.read_bytes()

    dump_resource_map(data)
    dump_pointer_table(data, 0x1A2457C, 1293 + 1, "levelup-pointer-table.json")
    dump_sparse_pair_table(data, 0x1A32BDC, 413, "learnset-sparse-pair-table.json")
    raw_region_files = dump_regions(data)
    write_manifest(decoded_files, raw_region_files)

    print(f"Wrote research bundle to {BUNDLE_DIR}")


if __name__ == "__main__":
    main()
