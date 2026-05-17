from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
OUTPUT_DIR = PUBLIC_DIR / "extracted"

DPE_DIR = PUBLIC_DIR / "Dynamic-Pokemon-Expansion"
CFRU_DIR = PUBLIC_DIR / "Complete-Fire-Red-Upgrade"

SPECIES_HEADER_PATH = DPE_DIR / "include" / "species.h"
MOVES_HEADER_PATH = CFRU_DIR / "include" / "constants" / "moves.h"
ABILITIES_HEADER_PATH = DPE_DIR / "include" / "abilities.h"
ITEMS_HEADER_PATH = DPE_DIR / "include" / "items.h"

SPECIES_NAMES_PATH = DPE_DIR / "strings" / "Pokemon_Name_Table.string"
MOVE_NAMES_PATH = CFRU_DIR / "strings" / "attack_name_table.string"
ABILITY_NAMES_PATH = CFRU_DIR / "strings" / "ability_name_table.string"

BASE_STATS_PATH = DPE_DIR / "src" / "Base_Stats.c"
EVOLUTIONS_PATH = DPE_DIR / "src" / "Evolution Table.c"
LEARNSETS_PATH = DPE_DIR / "src" / "Learnsets.c"
MOVE_DATA_PATH = CFRU_DIR / "src" / "Tables" / "battle_moves.c"
EGG_MOVES_PATH = DPE_DIR / "src" / "Egg_Moves.c"
TM_COMPAT_DIR = DPE_DIR / "src" / "tm_compatibility"
TUTOR_COMPAT_DIR = DPE_DIR / "src" / "tutor_compatibility"

TYPE_ID_TO_NAME = {
    0x00: "Normal",
    0x01: "Fighting",
    0x02: "Flying",
    0x03: "Poison",
    0x04: "Ground",
    0x05: "Rock",
    0x06: "Bug",
    0x07: "Ghost",
    0x08: "Steel",
    0x09: "Mystery",
    0x0A: "Fire",
    0x0B: "Water",
    0x0C: "Grass",
    0x0D: "Electric",
    0x0E: "Psychic",
    0x0F: "Ice",
    0x10: "Dragon",
    0x11: "Dark",
    0x12: "Fairy",
}
TYPE_TOKEN_TO_ID = {f"TYPE_{name.upper()}": value for value, name in TYPE_ID_TO_NAME.items()}
TYPE_TOKEN_TO_NAME = {token: TYPE_ID_TO_NAME[value] for token, value in TYPE_TOKEN_TO_ID.items()}

MOVE_CATEGORY_TOKEN_TO_NAME = {
    "SPLIT_PHYSICAL": "physical",
    "SPLIT_SPECIAL": "special",
    "SPLIT_STATUS": "status",
}
MOVE_CATEGORY_NAME_TO_ID = {
    "physical": 0,
    "special": 1,
    "status": 2,
}

EVOLUTION_METHOD_LABELS = {
    "EVO_NONE": "none",
    "EVO_FRIENDSHIP": "friendship",
    "EVO_FRIENDSHIP_DAY": "friendship-day",
    "EVO_FRIENDSHIP_NIGHT": "friendship-night",
    "EVO_LEVEL": "level",
    "EVO_TRADE": "trade",
    "EVO_TRADE_ITEM": "trade-item",
    "EVO_ITEM": "item",
    "EVO_LEVEL_ATK_GT_DEF": "level-atk-gt-def",
    "EVO_LEVEL_ATK_EQ_DEF": "level-atk-eq-def",
    "EVO_LEVEL_ATK_LT_DEF": "level-atk-lt-def",
    "EVO_LEVEL_SILCOON": "level-silcoon",
    "EVO_LEVEL_CASCOON": "level-cascoon",
    "EVO_LEVEL_NINJASK": "level-ninjask",
    "EVO_LEVEL_SHEDINJA": "level-shedinja",
    "EVO_BEAUTY": "beauty",
    "EVO_RAINY_FOGGY_OW": "rainy-foggy-overworld",
    "EVO_MOVE_TYPE": "move-type",
    "EVO_TYPE_IN_PARTY": "type-in-party",
    "EVO_MAP": "map",
    "EVO_MALE_LEVEL": "male-level",
    "EVO_FEMALE_LEVEL": "female-level",
    "EVO_LEVEL_NIGHT": "level-night",
    "EVO_LEVEL_DAY": "level-day",
    "EVO_HOLD_ITEM_NIGHT": "hold-item-night",
    "EVO_HOLD_ITEM_DAY": "hold-item-day",
    "EVO_MOVE": "move",
    "EVO_OTHER_PARTY_MON": "other-party-mon",
    "EVO_LEVEL_SPECIFIC_TIME_RANGE": "level-time-range",
    "EVO_FLAG_SET": "flag-set",
    "EVO_CRITICAL_HIT": "critical-hit",
    "EVO_NATURE_HIGH": "nature-high",
    "EVO_NATURE_LOW": "nature-low",
    "EVO_DAMAGE_LOCATION": "damage-location",
    "EVO_ITEM_LOCATION": "item-location",
    "EVO_GIGANTAMAX": "gigantamax",
    "EVO_MEGA": "mega",
}


def parse_int_literal(value: str) -> int | None:
    value = value.strip()
    if re.fullmatch(r"0x[0-9A-Fa-f]+", value):
        return int(value, 16)
    if re.fullmatch(r"\d+", value):
        return int(value, 10)
    return None


def pretty_token_name(token: str, prefix: str) -> str:
    if token.startswith(prefix):
        token = token[len(prefix) :]
    return token.replace("_", " ").title()


def normalize_move_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def parse_define_map(path: Path, prefix: str) -> dict[str, int]:
    raw_values: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"#define\s+({prefix}[A-Z0-9_]+)\s+(.+)", line)
        if not match:
            continue
        token = match.group(1)
        if token in raw_values:
            continue
        raw_values[token] = match.group(2).split("//", 1)[0].strip()

    resolved: dict[str, int] = {}

    def resolve(token: str) -> int:
        if token in resolved:
            return resolved[token]
        raw = raw_values[token]
        number = parse_int_literal(raw)
        if number is not None:
            resolved[token] = number
            return number
        alias = raw.split()[0]
        if alias in raw_values:
            resolved[token] = resolve(alias)
            return resolved[token]
        raise ValueError(f"Unsupported define value for {token}: {raw}")

    for token in raw_values:
        resolve(token)

    return resolved


def build_canonical_id_map(token_to_id: dict[str, int]) -> dict[int, str]:
    id_to_token: dict[int, str] = {}
    for token, value in token_to_id.items():
        id_to_token.setdefault(value, token)
    return id_to_token


def parse_ordered_name_table(path: Path) -> list[str]:
    names: list[str] = []
    pending_name = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("#org @NAME_"):
            pending_name = True
            continue
        if not pending_name or not line or line.startswith("#"):
            continue
        names.append(line)
        pending_name = False

    return names


def parse_percent_female(value: str) -> int:
    match = re.fullmatch(r"PERCENT_FEMALE\(([\d.]+)\)", value.strip())
    if not match:
        raise ValueError(f"Unsupported gender ratio expression: {value}")
    percent = float(match.group(1))
    return min(254, int((percent * 255) / 100))


def parse_gender_ratio(value: str) -> int:
    value = value.strip()
    if value.startswith("PERCENT_FEMALE"):
        return parse_percent_female(value)
    if value == "MON_MALE":
        return 0x00
    if value == "MON_FEMALE":
        return 0xFE
    if value == "MON_GENDERLESS":
        return 0xFF
    return int(value)


def parse_bool(value: str) -> bool:
    value = value.strip()
    if value == "TRUE":
        return True
    if value == "FALSE":
        return False
    raise ValueError(f"Unsupported boolean token: {value}")


def parse_token_or_number(value: str, mapping: dict[str, int]) -> tuple[int | None, str | None]:
    value = value.strip()
    if value in mapping:
        return mapping[value], value
    number = parse_int_literal(value)
    if number is not None:
        return number, None
    if value in {"TRUE", "FALSE"}:
        return (1 if value == "TRUE" else 0), value
    return None, value


def load_indexes() -> dict[str, Any]:
    species_ids = parse_define_map(SPECIES_HEADER_PATH, "SPECIES_")
    move_ids = parse_define_map(MOVES_HEADER_PATH, "MOVE_")
    ability_ids = parse_define_map(ABILITIES_HEADER_PATH, "ABILITY_")
    item_ids = parse_define_map(ITEMS_HEADER_PATH, "ITEM_")

    species_names = parse_ordered_name_table(SPECIES_NAMES_PATH)
    move_names = parse_ordered_name_table(MOVE_NAMES_PATH)
    ability_names = parse_ordered_name_table(ABILITY_NAMES_PATH)
    if ability_names and ability_names[0] == "-------":
        ability_names[0] = "None"

    return {
        "speciesIds": species_ids,
        "speciesIdToToken": build_canonical_id_map(species_ids),
        "moveIds": move_ids,
        "moveIdToToken": build_canonical_id_map(move_ids),
        "abilityIds": ability_ids,
        "itemIds": item_ids,
        "speciesNames": species_names,
        "moveNames": move_names,
        "abilityNames": ability_names,
        "moveNameToId": {
            normalize_move_name(name): move_id for move_id, name in enumerate(move_names)
        },
    }


def get_species_name(species_id: int, indexes: dict[str, Any]) -> str:
    names: list[str] = indexes["speciesNames"]
    if 0 <= species_id < len(names):
        return names[species_id]
    token = indexes["speciesIdToToken"].get(species_id, f"SPECIES_{species_id}")
    return pretty_token_name(token, "SPECIES_")


def get_move_name(move_id: int, indexes: dict[str, Any]) -> str:
    names: list[str] = indexes["moveNames"]
    if 0 <= move_id < len(names):
        return names[move_id]
    token = indexes["moveIdToToken"].get(move_id, f"MOVE_{move_id}")
    return pretty_token_name(token, "MOVE_")


def parse_base_stats(indexes: dict[str, Any]) -> list[dict[str, Any]]:
    species_ids: dict[str, int] = indexes["speciesIds"]
    ability_ids: dict[str, int] = indexes["abilityIds"]
    item_ids: dict[str, int] = indexes["itemIds"]
    ability_names: list[str] = indexes["abilityNames"]

    text = BASE_STATS_PATH.read_text(encoding="utf-8")
    block_pattern = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\{(.*?)\n\s*\},", re.S)
    field_pattern = re.compile(r"\.(\w+)\s*=\s*([^,\n]+)")

    rows: list[dict[str, Any]] = []
    for match in block_pattern.finditer(text):
        species_token = match.group(1)
        if species_token not in species_ids:
            continue
        species_id = species_ids[species_token]
        body = match.group(2)
        fields = {name: value.strip() for name, value in field_pattern.findall(body)}

        type1_token = fields.get("type1", "TYPE_MYSTERY")
        type2_token = fields.get("type2", "TYPE_MYSTERY")
        ability1_token = fields.get("ability1", "ABILITY_NONE")
        ability2_token = fields.get("ability2", "ABILITY_NONE")
        hidden_ability_token = fields.get("hiddenAbility", "ABILITY_NONE")
        item1_token = fields.get("item1", "ITEM_NONE")
        item2_token = fields.get("item2", "ITEM_NONE")

        ability1_id = ability_ids.get(ability1_token, 0)
        ability2_id = ability_ids.get(ability2_token, 0)
        hidden_ability_id = ability_ids.get(hidden_ability_token, 0)
        item1_id = item_ids.get(item1_token, 0)
        item2_id = item_ids.get(item2_token, 0)

        rows.append(
            {
                "speciesId": species_id,
                "name": get_species_name(species_id, indexes),
                "baseStats": {
                    "hp": int(fields.get("baseHP", "0")),
                    "atk": int(fields.get("baseAttack", "0")),
                    "def": int(fields.get("baseDefense", "0")),
                    "spe": int(fields.get("baseSpeed", "0")),
                    "spa": int(fields.get("baseSpAttack", "0")),
                    "spd": int(fields.get("baseSpDefense", "0")),
                },
                "types": [
                    TYPE_TOKEN_TO_NAME.get(type1_token, pretty_token_name(type1_token, "TYPE_")),
                    TYPE_TOKEN_TO_NAME.get(type2_token, pretty_token_name(type2_token, "TYPE_")),
                ],
                "catchRate": int(fields.get("catchRate", "0")),
                "expYield": int(fields.get("expYield", "0")),
                "evYield": {
                    "hp": int(fields.get("evYield_HP", "0")),
                    "atk": int(fields.get("evYield_Attack", "0")),
                    "def": int(fields.get("evYield_Defense", "0")),
                    "spe": int(fields.get("evYield_Speed", "0")),
                    "spa": int(fields.get("evYield_SpAttack", "0")),
                    "spd": int(fields.get("evYield_SpDefense", "0")),
                },
                "heldItem1Id": item1_id,
                "heldItem1Name": pretty_token_name(item1_token, "ITEM_") if item1_id else None,
                "heldItem2Id": item2_id,
                "heldItem2Name": pretty_token_name(item2_token, "ITEM_") if item2_id else None,
                "genderRatio": parse_gender_ratio(fields.get("genderRatio", "0")),
                "eggCycles": int(fields.get("eggCycles", "0")),
                "friendship": int(fields.get("friendship", "0")),
                "growthRateToken": fields.get("growthRate"),
                "eggGroup1Token": fields.get("eggGroup1"),
                "eggGroup2Token": fields.get("eggGroup2"),
                "ability1Id": ability1_id,
                "ability1Name": ability_names[ability1_id] if ability1_id < len(ability_names) else pretty_token_name(ability1_token, "ABILITY_"),
                "ability2Id": ability2_id,
                "ability2Name": ability_names[ability2_id] if 0 < ability2_id < len(ability_names) else None,
                "hiddenAbilityId": hidden_ability_id,
                "hiddenAbilityName": ability_names[hidden_ability_id] if 0 < hidden_ability_id < len(ability_names) else None,
                "safariFleeRate": int(fields.get("safariZoneFleeRate", "0")),
                "noFlip": parse_bool(fields.get("noFlip", "FALSE")),
                "source": {
                    "kind": "source-table",
                    "file": str(BASE_STATS_PATH.relative_to(BASE_DIR)),
                    "symbol": "gBaseStats",
                },
            }
        )

    rows.sort(key=lambda row: row["speciesId"])
    return rows


def parse_moves(indexes: dict[str, Any]) -> list[dict[str, Any]]:
    move_ids: dict[str, int] = indexes["moveIds"]
    text = MOVE_DATA_PATH.read_text(encoding="utf-8")
    block_pattern = re.compile(r"\[(MOVE_[A-Z0-9_]+)\]\s*=\s*\{(.*?)\n\s*\},", re.S)
    field_pattern = re.compile(r"\.(\w+)\s*=\s*([^,\n]+)")

    rows: list[dict[str, Any]] = []
    for fallback_move_id, match in enumerate(block_pattern.finditer(text)):
        move_token = match.group(1)
        move_id = move_ids.get(move_token, fallback_move_id)
        body = match.group(2)
        fields = {name: value.strip() for name, value in field_pattern.findall(body)}
        type_token = fields.get("type", "TYPE_MYSTERY")
        category_token = fields.get("split", "SPLIT_STATUS")
        category_name = MOVE_CATEGORY_TOKEN_TO_NAME.get(category_token, "status")

        rows.append(
            {
                "moveId": move_id,
                "name": get_move_name(move_id, indexes),
                "effectToken": fields.get("effect"),
                "power": int(fields.get("power", "0")),
                "typeId": TYPE_TOKEN_TO_ID.get(type_token, 0x09),
                "typeName": TYPE_TOKEN_TO_NAME.get(type_token, pretty_token_name(type_token, "TYPE_")),
                "accuracy": int(fields.get("accuracy", "0")),
                "pp": int(fields.get("pp", "0")),
                "effectChance": int(fields.get("secondaryEffectChance", "0")),
                "priority": int(fields.get("priority", "0")),
                "targetToken": fields.get("target"),
                "categoryId": MOVE_CATEGORY_NAME_TO_ID[category_name],
                "categoryName": category_name,
                "source": {
                    "kind": "source-table",
                    "file": str(MOVE_DATA_PATH.relative_to(BASE_DIR)),
                    "symbol": "gBattleMoves",
                },
            }
        )

    rows.sort(key=lambda row: row["moveId"])
    return rows


def parse_level_up_learnsets(indexes: dict[str, Any]) -> list[dict[str, Any]]:
    species_ids: dict[str, int] = indexes["speciesIds"]
    move_ids: dict[str, int] = indexes["moveIds"]
    text = LEARNSETS_PATH.read_text(encoding="utf-8")
    array_pattern = re.compile(r"static const struct LevelUpMove (\w+)\[\]\s*=\s*\{(.*?)\};", re.S)
    move_pattern = re.compile(r"LEVEL_UP_MOVE\(\s*(\d+)\s*,\s*(MOVE_[A-Z0-9_]+)\s*\)")
    mapping_pattern = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*(\w+)")

    arrays: dict[str, list[dict[str, Any]]] = {}
    for match in array_pattern.finditer(text):
        array_name = match.group(1)
        body = match.group(2)
        entries: list[dict[str, Any]] = []
        for level, move_token in move_pattern.findall(body):
            move_id = move_ids.get(move_token)
            if move_id is None:
                continue
            entries.append(
                {
                    "level": int(level),
                    "moveId": move_id,
                    "moveName": get_move_name(move_id, indexes),
                    "moveToken": move_token,
                    "source": "level-up",
                }
            )
        arrays[array_name] = entries

    species_to_array = {
        species_token: array_name
        for species_token, array_name in mapping_pattern.findall(text)
        if species_token in species_ids
    }

    rows: list[dict[str, Any]] = []
    seen_species: set[int] = set()
    for species_token, array_name in species_to_array.items():
        species_id = species_ids[species_token]
        seen_species.add(species_id)
        rows.append(
            {
                "speciesId": species_id,
                "speciesName": get_species_name(species_id, indexes),
                "moves": arrays.get(array_name, []),
                "source": {
                    "kind": "source-table",
                    "file": str(LEARNSETS_PATH.relative_to(BASE_DIR)),
                    "symbol": "gLevelUpLearnsets",
                    "array": array_name,
                },
            }
        )

    rows.sort(key=lambda row: row["speciesId"])
    return rows


def parse_evolutions(indexes: dict[str, Any]) -> list[dict[str, Any]]:
    species_ids: dict[str, int] = indexes["speciesIds"]
    item_ids: dict[str, int] = indexes["itemIds"]

    evolutions_by_species: dict[int, list[dict[str, Any]]] = {}
    current_species_id: int | None = None

    for raw_line in EVOLUTIONS_PATH.read_text(encoding="utf-8").splitlines():
        species_match = re.search(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=", raw_line)
        if species_match:
            species_token = species_match.group(1)
            current_species_id = species_ids.get(species_token)
            if current_species_id is not None:
                evolutions_by_species.setdefault(current_species_id, [])

        if current_species_id is None:
            continue

        for entry_body in re.findall(r"\{([^{}]+)\}", raw_line):
            parts = [part.strip() for part in entry_body.split(",")]
            if len(parts) != 4 or not parts[0].startswith("EVO_"):
                continue

            method_token, param_raw, target_species_token, unknown_raw = parts
            target_species_id = species_ids.get(target_species_token)
            param_id, param_token = parse_token_or_number(param_raw, item_ids)
            unknown_id, unknown_token = parse_token_or_number(unknown_raw, species_ids | item_ids)

            evolutions_by_species[current_species_id].append(
                {
                    "methodToken": method_token,
                    "method": EVOLUTION_METHOD_LABELS.get(method_token, method_token),
                    "param": param_id,
                    "paramToken": param_token or (param_raw if param_id is None else None),
                    "paramLabel": pretty_token_name(param_token, "ITEM_") if param_token and param_token.startswith("ITEM_") else (TYPE_TOKEN_TO_NAME.get(param_raw) if param_raw.startswith("TYPE_") else None),
                    "targetSpeciesId": target_species_id,
                    "targetSpeciesName": get_species_name(target_species_id, indexes) if target_species_id is not None else pretty_token_name(target_species_token, "SPECIES_"),
                    "targetSpeciesToken": target_species_token,
                    "unknown": unknown_id,
                    "unknownToken": unknown_token or (unknown_raw if unknown_id is None else None),
                }
            )

    rows: list[dict[str, Any]] = []
    for species_id in sorted(evolutions_by_species):
        rows.append(
            {
                "speciesId": species_id,
                "speciesName": get_species_name(species_id, indexes),
                "evolutions": evolutions_by_species.get(species_id, []),
                "source": {
                    "kind": "source-table",
                    "file": str(EVOLUTIONS_PATH.relative_to(BASE_DIR)),
                    "symbol": "gEvolutionTable",
                },
            }
        )

    return rows


def parse_egg_moves(indexes: dict[str, Any]) -> list[dict[str, Any]]:
    species_ids: dict[str, int] = indexes["speciesIds"]
    move_ids: dict[str, int] = indexes["moveIds"]
    text = EGG_MOVES_PATH.read_text(encoding="utf-8")
    block_pattern = re.compile(r"egg_moves\(([A-Z0-9_]+),(.*?)\),", re.S)

    rows: list[dict[str, Any]] = []
    for match in block_pattern.finditer(text):
        species_name_token = match.group(1)
        species_token = f"SPECIES_{species_name_token}"
        species_id = species_ids.get(species_token)
        if species_id is None:
            continue

        body = match.group(2)
        moves: list[dict[str, Any]] = []
        for move_token in re.findall(r"(MOVE_[A-Z0-9_]+)", body):
            move_id = move_ids.get(move_token)
            if move_id is None:
                continue
            moves.append(
                {
                    "moveId": move_id,
                    "moveName": get_move_name(move_id, indexes),
                    "moveToken": move_token,
                    "source": "egg",
                }
            )

        rows.append(
            {
                "speciesId": species_id,
                "speciesName": get_species_name(species_id, indexes),
                "moves": moves,
                "source": {
                    "kind": "source-table",
                    "file": str(EGG_MOVES_PATH.relative_to(BASE_DIR)),
                    "symbol": "gEggMoves",
                },
            }
        )

    rows.sort(key=lambda row: row["speciesId"])
    return rows


def parse_compatibility_dir(directory: Path, indexes: dict[str, Any], learnset_source: str) -> list[dict[str, Any]]:
    species_ids: dict[str, int] = indexes["speciesIds"]
    move_name_to_id: dict[str, int] = indexes["moveNameToId"]
    per_species: dict[int, list[dict[str, Any]]] = {}

    for path in sorted(directory.glob("*.txt")):
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            continue

        header = lines[0]
        header_match = re.match(r"(?:TM|Tutor)\s*(\d+)\s*:\s*(.+)", header, re.I)
        if header_match:
            slot = int(header_match.group(1))
            move_name = header_match.group(2).strip()
        else:
            file_match = re.match(r"(\d+)\s*-\s*(.+)\.txt", path.name)
            if not file_match:
                continue
            slot = int(file_match.group(1))
            move_name = file_match.group(2).strip()

        move_id = move_name_to_id.get(normalize_move_name(move_name))
        if move_id is None:
            continue

        for species_line in lines[1:]:
            species_token = species_line if species_line.startswith("SPECIES_") else f"SPECIES_{species_line}"
            species_id = species_ids.get(species_token)
            if species_id is None:
                continue
            per_species.setdefault(species_id, []).append(
                {
                    "slot": slot,
                    "moveId": move_id,
                    "moveName": get_move_name(move_id, indexes),
                    "moveToken": indexes["moveIdToToken"].get(move_id),
                    "source": learnset_source,
                }
            )

    rows = [
        {
            "speciesId": species_id,
            "speciesName": get_species_name(species_id, indexes),
            "moves": sorted(entries, key=lambda entry: (entry["slot"], entry["moveId"])),
            "source": {
                "kind": "source-table",
                "file": str(directory.relative_to(BASE_DIR)),
            },
        }
        for species_id, entries in sorted(per_species.items())
    ]
    return rows


def combine_learnsets(
    level_up: list[dict[str, Any]],
    egg: list[dict[str, Any]],
    tm: list[dict[str, Any]],
    tutor: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined: dict[int, dict[str, Any]] = {}

    for dataset in (level_up, egg, tm, tutor):
        for row in dataset:
            entry = combined.setdefault(
                row["speciesId"],
                {
                    "speciesId": row["speciesId"],
                    "speciesName": row["speciesName"],
                    "moves": [],
                },
            )
            entry["moves"].extend(row["moves"])

    for row in combined.values():
        seen: set[tuple[Any, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for move in row["moves"]:
            key = (
                move["source"],
                move["moveId"],
                move.get("level"),
                move.get("slot"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(move)
        row["moves"] = deduped
        row["source"] = {"kind": "combined-source-tables"}

    return [combined[species_id] for species_id in sorted(combined)]


def parse_referenced_items(
    species: list[dict[str, Any]],
    evolutions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: dict[int, str] = {}

    for entry in species:
        for item_id_key, item_name_key in (("heldItem1Id", "heldItem1Name"), ("heldItem2Id", "heldItem2Name")):
            item_id = entry.get(item_id_key) or 0
            item_name = entry.get(item_name_key)
            if item_id and item_name:
                items[item_id] = item_name

    for entry in evolutions:
        for evolution in entry["evolutions"]:
            item_id = evolution.get("param")
            item_label = evolution.get("paramLabel")
            if isinstance(item_id, int) and item_id > 0 and item_label:
                items[item_id] = item_label

    return [
        {"itemId": item_id, "name": name}
        for item_id, name in sorted(items.items(), key=lambda pair: pair[0])
    ]


def build_summary(
    species: list[dict[str, Any]],
    moves: list[dict[str, Any]],
    abilities: list[dict[str, Any]],
    items: list[dict[str, Any]],
    evolutions: list[dict[str, Any]],
    level_up: list[dict[str, Any]],
    egg: list[dict[str, Any]],
    tm: list[dict[str, Any]],
    tutor: list[dict[str, Any]],
    combined: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source": {
            "primaryDataset": "Skeli789 source repositories",
            "repositories": [
                str(DPE_DIR.relative_to(BASE_DIR)),
                str(CFRU_DIR.relative_to(BASE_DIR)),
            ],
            "romUsed": False,
        },
        "generatedFiles": [
            "/extracted/summary.json",
            "/extracted/species.json",
            "/extracted/moves.json",
            "/extracted/abilities.json",
            "/extracted/items-partial.json",
            "/extracted/evolutions.json",
            "/extracted/learnsets-level.json",
            "/extracted/learnsets-egg.json",
            "/extracted/learnsets-tm.json",
            "/extracted/learnsets-tutor.json",
            "/extracted/learnsets-combined.json",
        ],
        "sections": {
            "species": {
                "status": "source-extracted",
                "count": len(species),
                "notes": [
                    "Species names and base stats are extracted from the Dynamic Pokemon Expansion source tables.",
                ],
            },
            "moves": {
                "status": "source-extracted",
                "count": len(moves),
                "notes": [
                    "Move names come from CFRU string tables and battle metadata comes from the CFRU move table.",
                ],
            },
            "abilities": {
                "status": "source-extracted",
                "count": len(abilities),
                "notes": [
                    "Ability names are extracted from the CFRU string tables.",
                ],
            },
            "items": {
                "status": "source-referenced",
                "count": len(items),
                "notes": [
                    "Only items referenced by extracted species or evolution data are exported here.",
                ],
            },
            "evolutions": {
                "status": "source-extracted",
                "count": sum(len(entry["evolutions"]) for entry in evolutions),
                "notes": [
                    "Evolution methods are extracted directly from the Dynamic Pokemon Expansion evolution table.",
                ],
            },
            "learnsetsLevel": {
                "status": "source-extracted",
                "count": len(level_up),
                "notes": [
                    "Level-up learnsets are extracted from the Dynamic Pokemon Expansion learnset tables.",
                ],
            },
            "learnsetsEgg": {
                "status": "source-extracted",
                "count": len(egg),
                "notes": [
                    "Egg moves are extracted from the Dynamic Pokemon Expansion egg move table.",
                ],
            },
            "learnsetsTmHm": {
                "status": "source-extracted",
                "count": len(tm),
                "notes": [
                    "TM/HM compatibility is extracted from the Dynamic Pokemon Expansion per-move text files.",
                ],
            },
            "learnsetsTutor": {
                "status": "source-extracted",
                "count": len(tutor),
                "notes": [
                    "Tutor compatibility is extracted from the Dynamic Pokemon Expansion per-move text files.",
                ],
            },
            "learnsetsCombined": {
                "status": "source-extracted",
                "count": len(combined),
                "notes": [
                    "Combined per-species learnsets include level-up, egg, TM/HM, and tutor sources.",
                ],
            },
        },
    }


def main() -> None:
    indexes = load_indexes()

    species = parse_base_stats(indexes)
    moves = parse_moves(indexes)
    abilities = [
        {"abilityId": ability_id, "name": name}
        for ability_id, name in enumerate(indexes["abilityNames"])
    ]
    evolutions = parse_evolutions(indexes)
    level_up = parse_level_up_learnsets(indexes)
    egg = parse_egg_moves(indexes)
    tm = parse_compatibility_dir(TM_COMPAT_DIR, indexes, "tm")
    tutor = parse_compatibility_dir(TUTOR_COMPAT_DIR, indexes, "tutor")
    combined = combine_learnsets(level_up, egg, tm, tutor)
    items = parse_referenced_items(species, evolutions)
    summary = build_summary(species, moves, abilities, items, evolutions, level_up, egg, tm, tutor, combined)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "summary.json": summary,
        "species.json": species,
        "moves.json": moves,
        "abilities.json": abilities,
        "items-partial.json": items,
        "evolutions.json": evolutions,
        "learnsets-level.json": level_up,
        "learnsets-egg.json": egg,
        "learnsets-tm.json": tm,
        "learnsets-tutor.json": tutor,
        "learnsets-combined.json": combined,
    }

    for filename, payload in outputs.items():
        with (OUTPUT_DIR / filename).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    print(f"Wrote source-backed extracted data to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
