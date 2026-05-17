from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = BASE_DIR / "public" / "extracted" / "gym-leaders.json"

USER_AGENT = "Mozilla/5.0 (compatible; Codex Gym Leader Scraper/1.0)"

GYMS = [
    {
        "gymNumber": 1,
        "location": "Dresco Town",
        "badge": "Leaf Badge",
        "gymType": "Grass",
        "leader": "Mirskle",
        "townPage": "Dresco_Town",
        "gymPage": "Dresco_Town/Dresco_Town_Gym",
    },
    {
        "gymNumber": 2,
        "location": "Crater Town",
        "badge": "Vision Badge",
        "gymType": "Dark",
        "leader": "Véga",
        "townPage": "Crater_Town",
        "gymPage": "Crater_Town/Crater_Town_Gym",
    },
    {
        "gymNumber": 3,
        "location": "Blizzard City",
        "badge": "Wings Badge",
        "gymType": "Flying",
        "leader": "Alice",
        "townPage": "Blizzard_City",
        "gymPage": "Blizzard_City/Blizzard_City_Gym",
    },
    {
        "gymNumber": 4,
        "location": "Fallshore City",
        "badge": "Fall Badge",
        "gymType": "Normal",
        "leader": "Mel",
        "townPage": "Fallshore_City",
        "gymPage": "Fallshore_City/Fallshore_City_Gym",
    },
    {
        "gymNumber": 5,
        "location": "Dehara City",
        "badge": "Battery Badge",
        "gymType": "Electric",
        "leader": "Galavan",
        "townPage": "Dehara_City",
        "gymPage": "Dehara_City/Dehara_City_Gym",
    },
    {
        "gymNumber": 6,
        "location": "Antisis City",
        "badge": "Ring Badge",
        "gymType": "Fighting",
        "leader": "Big Mo",
        "townPage": "Antisis_City",
        "gymPage": "Antisis_City/Antisis_City_Gym",
    },
    {
        "gymNumber": 7,
        "location": "Polder Town",
        "badge": "Swamp Badge",
        "gymType": "Water",
        "leader": "Tessy",
        "townPage": "Polder_Town",
        "gymPage": "Polder_Town/Polder_Town_Gym",
    },
    {
        "gymNumber": 8,
        "location": "Redwood Village",
        "badge": "Time Badge",
        "gymType": "Psychic",
        "leader": "Benjamin",
        "townPage": "Redwood_Village",
        "gymPage": "Redwood_Village/Redwood_Village_Gym",
    },
]


def fetch_raw_wiki(page: str) -> str:
    url = f"https://pokemonunbound.miraheze.org/wiki/{urllib.parse.quote(page, safe='/')}?action=raw"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "ignore")


def parse_infobox_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\|{re.escape(key)}\s*=\s*(.+)$", text, re.M)
    if not match:
        return None
    return clean_value(match.group(1))


def clean_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    value = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\{\{!}}", "|", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = re.sub(r"}+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_template(text: str, start_index: int) -> tuple[str, int]:
    depth = 0
    i = start_index
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return text[start_index:i], i
            continue
        i += 1
    raise ValueError("Unclosed template")


def parse_template_params(template_text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    matches = list(re.finditer(r"\|\s*([A-Za-z0-9_]+)\s*=", template_text))
    for index, match in enumerate(matches):
        key = match.group(1).strip()
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(template_text)
        value = template_text[value_start:value_end]
        params[key] = clean_value(value)
    return params


def parse_pokemon_template(template_text: str) -> dict[str, Any]:
    params = parse_template_params(template_text)
    moves: list[dict[str, str]] = []
    for index in range(1, 5):
        move_name = params.get(f"move{index}")
        if not move_name:
            continue
        moves.append(
            {
                "name": move_name,
                "type": params.get(f"move{index}type", ""),
                "category": params.get(f"move{index}cat", ""),
            }
        )

    type_values = [params.get("type1", "")]
    if params.get("type2"):
        type_values.append(params["type2"])

    return {
        "nationalDex": int(params["ndex"]) if params.get("ndex", "").isdigit() else None,
        "pokemon": params.get("pokemon"),
        "form": params.get("form") or None,
        "level": int(params["level"]) if params.get("level", "").isdigit() else None,
        "gender": params.get("gender") or None,
        "types": [value for value in type_values if value],
        "ability": params.get("ability") or None,
        "abilityMega": params.get("abilitymega") or None,
        "nature": params.get("nature") or None,
        "heldItem": params.get("held") or None,
        "evSpread": params.get("evSpread") or None,
        "ivs": params.get("ivs") or None,
        "moves": moves,
    }


def parse_gym_page(page_text: str) -> list[dict[str, Any]]:
    parties: list[dict[str, Any]] = []
    index = 0

    while True:
        start = page_text.find("{{Party/", index)
        if start == -1:
            break

        template_text, next_index = extract_template(page_text, start)
        if template_text.startswith("{{Party/Single") or template_text.startswith("{{Party/Double"):
            header = parse_template_params(template_text)
            battle_type = "double" if template_text.startswith("{{Party/Double") else "single"
            party = {
                "battleType": battle_type,
                "difficulty": header.get("difficulty"),
                "trainerName": header.get("name"),
                "trainerClass": header.get("class"),
                "location": header.get("location"),
                "prize": header.get("prize"),
                "pokemonCount": int(header["pokemon"]) if header.get("pokemon", "").isdigit() else None,
                "team": [],
            }

            scan_index = next_index
            while True:
                pokemon_start = page_text.find("{{Pokémon/TrainerBoss", scan_index)
                next_single_start = page_text.find("{{Party/Single", scan_index)
                next_double_start = page_text.find("{{Party/Double", scan_index)
                next_heading = page_text.find("===", scan_index)
                boundary_candidates = [
                    value
                    for value in [next_single_start, next_double_start, next_heading]
                    if value != -1
                ]
                boundary = min(boundary_candidates) if boundary_candidates else len(page_text)

                if pokemon_start == -1 or pokemon_start >= boundary:
                    break

                pokemon_template, pokemon_end = extract_template(page_text, pokemon_start)
                party["team"].append(parse_pokemon_template(pokemon_template))
                scan_index = pokemon_end

            parties.append(party)

        index = next_index

    return parties


def scrape_gym(gym: dict[str, Any]) -> dict[str, Any]:
    town_raw = fetch_raw_wiki(gym["townPage"])
    gym_raw = fetch_raw_wiki(gym["gymPage"])

    badge = parse_infobox_value(town_raw, "badge") or gym["badge"]
    gym_type = parse_infobox_value(town_raw, "gymtype") or gym["gymType"]
    leader = parse_infobox_value(town_raw, "leader") or gym["leader"]
    gym_number = parse_infobox_value(town_raw, "gymno")

    return {
        "gymNumber": int(gym_number) if gym_number and gym_number.isdigit() else gym["gymNumber"],
        "location": gym["location"],
        "leader": leader,
        "badge": f"{badge} Badge" if badge and not badge.endswith("Badge") else badge,
        "gymType": gym_type,
        "sources": {
            "townPage": f"https://pokemonunbound.miraheze.org/wiki/{gym['townPage']}",
            "gymPage": f"https://pokemonunbound.miraheze.org/wiki/{gym['gymPage']}",
            "townRaw": f"https://pokemonunbound.miraheze.org/wiki/{gym['townPage']}?action=raw",
            "gymRaw": f"https://pokemonunbound.miraheze.org/wiki/{gym['gymPage']}?action=raw",
        },
        "difficulties": parse_gym_page(gym_raw),
    }


def main() -> None:
    gyms = [scrape_gym(gym) for gym in GYMS]

    payload = {
        "source": "pokemonunbound.miraheze.org",
        "generatedAtNote": "Generated from raw wiki pages via action=raw",
        "gyms": gyms,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"Wrote gym leader data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
