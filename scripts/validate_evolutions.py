from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = BASE_DIR / "public" / "extracted"
EVOLUTIONS_PATH = EXTRACTED_DIR / "evolutions.json"
SPECIES_PATH = EXTRACTED_DIR / "species.json"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def main() -> int:
    evolutions = load_json(EVOLUTIONS_PATH)
    species = load_json(SPECIES_PATH)

    species_by_id = {row["speciesId"]: row for row in species}
    findings: list[str] = []

    seen_edges_by_source: dict[int, set[tuple[Any, ...]]] = defaultdict(set)
    incoming_counts: dict[int, int] = defaultdict(int)

    for record in evolutions:
        source_id = record["speciesId"]
        source_name = record["speciesName"]
        source_species = species_by_id.get(source_id)

        if source_species is None:
            findings.append(
                f"[missing-source] {source_name} ({source_id}) does not exist in species.json"
            )
            continue

        for evolution in record["evolutions"]:
            target_id = evolution["targetSpeciesId"]
            target_name = evolution["targetSpeciesName"]
            method = evolution["method"]
            param_label = evolution.get("paramLabel")

            if target_id not in species_by_id:
                findings.append(
                    f"[missing-target] {source_name} ({source_id}) -> {target_name} ({target_id})"
                )
                continue

            target_species = species_by_id[target_id]
            display_target_name = target_species.get("displayName", target_species["name"])

            edge_key = (
                method,
                evolution.get("param"),
                param_label,
                target_id,
            )
            if edge_key in seen_edges_by_source[source_id]:
                findings.append(
                    f"[duplicate-edge] {source_name} ({source_id}) -> {display_target_name} ({target_id}) via {method}"
                )
            else:
                seen_edges_by_source[source_id].add(edge_key)

            incoming_counts[target_id] += 1

            if source_id == target_id:
                findings.append(
                    f"[self-target] {source_name} ({source_id}) points to itself via {method}"
                )

            if method in {"base", "none", "babyform"}:
                findings.append(
                    f"[suspicious-method] {source_name} ({source_id}) -> {display_target_name} ({target_id}) uses {method}"
                )

            if normalize_name(target_name) not in {
                normalize_name(target_species["name"]),
                normalize_name(target_species.get("displayName", "")),
            }:
                findings.append(
                    f"[name-mismatch] {source_name} ({source_id}) -> {target_name} ({target_id}), species.json says {display_target_name}"
                )

            if method == "item" and not param_label:
                findings.append(
                    f"[missing-item-label] {source_name} ({source_id}) -> {display_target_name} ({target_id})"
                )

            if "trade" in method and source_species.get("sourceNationalDex") == target_species.get("sourceNationalDex"):
                findings.append(
                    f"[same-dex-trade] {source_name} ({source_id}) -> {display_target_name} ({target_id})"
                )

    for row in species:
        if row["speciesId"] in seen_edges_by_source and row["speciesId"] in incoming_counts:
            continue
        if row["speciesId"] not in seen_edges_by_source:
            continue
        if len(seen_edges_by_source[row["speciesId"]]) == 0:
            findings.append(
                f"[empty-evolution-list] {row.get('displayName', row['name'])} ({row['speciesId']}) has an exported record with no edges"
            )

    if findings:
        print("Evolution validation findings:")
        for finding in sorted(findings):
            print(f"- {finding}")
        return 1

    print("Evolution validation passed with no findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
