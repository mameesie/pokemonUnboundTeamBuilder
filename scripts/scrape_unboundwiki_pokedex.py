from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import extract_unbound_data as source_data

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "public" / "extracted"
CACHE_DIR = BASE_DIR / ".cache" / "unboundwiki"
INDEX_URL = "https://unboundwiki.com/pokemon/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
REQUEST_DELAY_SECONDS = 0.15
MAX_WORKERS = 6
RESEARCH_SPECIES_PATH = BASE_DIR / "research" / "unbound-bundle" / "decoded" / "species.json"
REGIONAL_PREFIXES = ("Alolan ", "Galarian ", "Hisuian ", "Paldean ")

POKEMON_TYPES = {
    "Normal",
    "Fire",
    "Water",
    "Electric",
    "Grass",
    "Ice",
    "Fighting",
    "Poison",
    "Ground",
    "Flying",
    "Psychic",
    "Bug",
    "Rock",
    "Ghost",
    "Dragon",
    "Dark",
    "Steel",
    "Fairy",
}


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def slugify(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("♀", "-f")
        .replace("♂", "-m")
        .replace(".", "")
        .replace("'", "")
        .replace(":", "")
        .replace("%", " percent")
        .replace("é", "e")
    )


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_tabbed_row(line: str) -> list[str]:
    parts = [collapse_spaces(part) for part in line.split("\t")]
    return [part for part in parts if part]


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


class BlockTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br"}:
            self.parts.append("\n")
        elif tag in {"tr"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")
        elif tag in {"p", "div", "section", "article", "ul", "ol", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"tr", "p", "div", "section", "article", "ul", "ol", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(unescape(data))

    def get_lines(self) -> list[str]:
        text = "".join(self.parts)
        raw_lines = text.splitlines()
        normalized_lines: list[str] = []
        for raw_line in raw_lines:
            line = collapse_spaces(raw_line.replace("\xa0", " "))
            line = re.sub(r"\t+", "\t", line).strip("\t ")
            if line:
                normalized_lines.append(line)
        return normalized_lines


@dataclass
class ScrapedMoveEntry:
    move_name: str
    level: int | None
    source: str


@dataclass
class ScrapedEvolutionEntry:
    source_name: str
    target_name: str
    method: str
    param: int | None
    param_label: str | None
    raw_acquire: str


@dataclass
class ScrapedPokemonPage:
    page_name: str
    page_url: str
    national_dex: int | None
    types: list[str]
    abilities: list[dict[str, str | None]]
    locations: list[str]
    level_up_moves: list[ScrapedMoveEntry]
    tm_moves: list[ScrapedMoveEntry]
    tutor_moves: list[ScrapedMoveEntry]
    egg_moves: list[ScrapedMoveEntry]
    evolutions: list[ScrapedEvolutionEntry]


def split_variant_name(name: str) -> tuple[str | None, str]:
    normalized = collapse_spaces(name)
    for prefix in REGIONAL_PREFIXES:
        if normalized.startswith(prefix):
            return prefix.strip(), normalized[len(prefix) :].strip()
    return None, normalized


def get_species_label(row: dict[str, Any]) -> str:
    display_name = row.get("displayName")
    if isinstance(display_name, str) and display_name:
        return display_name
    return row["name"]


def get_species_variant_prefix(row: dict[str, Any]) -> str | None:
    variant_prefix, _ = split_variant_name(get_species_label(row))
    return variant_prefix


def normalize_species_types(types: list[str]) -> tuple[str, ...]:
    filtered = [pokemon_type for pokemon_type in types if pokemon_type]
    if len(filtered) >= 2:
        return tuple(filtered[:2])
    if len(filtered) == 1:
        return (filtered[0], filtered[0])
    return tuple()


def normalize_ability_names(
    abilities: list[dict[str, str | None]] | list[str | None],
) -> set[str]:
    names: list[str] = []
    for ability in abilities:
        if isinstance(ability, dict):
            name = ability.get("name")
        else:
            name = ability
        if name:
            names.append(normalize_name(name))
    return set(names)


def choose_best_species_row(
    candidates: list[dict[str, Any]],
    *,
    requested_name: str | None = None,
    national_dex: int | None,
    page_types: list[str] | None = None,
    page_abilities: list[dict[str, str | None]] | None = None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    requested_types = normalize_species_types(page_types or [])
    requested_abilities = normalize_ability_names(page_abilities or [])
    requested_variant_prefix = None
    requested_normalized_name = None
    if requested_name:
        requested_variant_prefix, _ = split_variant_name(requested_name)
        requested_normalized_name = normalize_name(requested_name)

    scored_candidates: list[tuple[int, int, dict[str, Any]]] = []
    for row in candidates:
        score = 0
        row_label = get_species_label(row)
        row_variant_prefix = get_species_variant_prefix(row)
        if requested_normalized_name is not None:
            if normalize_name(row_label) == requested_normalized_name:
                score += 200
            elif normalize_name(row["name"]) == requested_normalized_name:
                score += 120

        if requested_variant_prefix is None:
            if row_variant_prefix is not None:
                score -= 150
        elif row_variant_prefix == requested_variant_prefix:
            score += 120
        elif row_variant_prefix is not None:
            score -= 150

        if national_dex is not None and row.get("sourceNationalDex") == national_dex:
            score += 100
        elif row.get("sourceNationalDex") is not None:
            score += 5
        if requested_types:
            row_types = normalize_species_types(row.get("types", []))
            if row_types == requested_types:
                score += 30
            elif set(row_types) == set(requested_types):
                score += 20
        if requested_abilities:
            row_abilities = normalize_ability_names(
                [
                    row.get("ability1Name"),
                    row.get("ability2Name"),
                    row.get("hiddenAbilityName"),
                ]
            )
            score += len(row_abilities & requested_abilities) * 10
        if row.get("wikiPage"):
            score += 2
        scored_candidates.append((score, row["speciesId"], row))

    scored_candidates.sort(key=lambda entry: (entry[0], -entry[1]), reverse=True)
    best_score, _, best_row = scored_candidates[0]
    if best_score > 0:
        return best_row
    return candidates[0]


def should_export_evolution_edge(
    source_species_id: int,
    target_species_id: int,
    method: str,
) -> bool:
    normalized_method = normalize_name(method)
    if source_species_id == target_species_id:
        return False
    if normalized_method in {"base", "babyform", "baseformbaby", "breed"}:
        return False
    return True


def canonicalize_evolution_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = collapse_spaces(value)
    cleaned = cleaned.replace("withi high friendship", "with high friendship")
    cleaned = cleaned.replace("withihighfriendship", "withhighfriendship")
    return cleaned


def load_research_species() -> list[dict[str, Any]]:
    if not RESEARCH_SPECIES_PATH.exists():
        return []
    with RESEARCH_SPECIES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def fetch_text(url: str, *, cache_key: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_key
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8", "ignore")
    cache_path.write_text(payload, encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return payload


def collect_pokemon_urls(index_html: str) -> list[str]:
    parser = LinkCollector()
    parser.feed(index_html)
    urls: set[str] = set()
    for href in parser.links:
        absolute = urllib.parse.urljoin(INDEX_URL, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.netloc != "unboundwiki.com":
            continue
        if not parsed.path.startswith("/pokemon/"):
            continue
        if parsed.path == "/pokemon/":
            continue
        if not parsed.path.endswith("/"):
            continue
        urls.add(f"https://unboundwiki.com{parsed.path}")
    return sorted(urls)


def find_line_index(lines: list[str], target: str) -> int:
    for index, line in enumerate(lines):
        if line == target:
            return index
    return -1


def find_any_line_index(lines: list[str], targets: set[str], start: int = 0) -> int:
    for index in range(start, len(lines)):
        if lines[index] in targets:
            return index
    return -1


def collect_section_lines(lines: list[str], heading: str) -> list[str]:
    start = find_line_index(lines, heading)
    if start == -1:
        return []

    result: list[str] = []
    section_headings = {
        "Evolution Line",
        "Moveset (Level Up)",
        "Learnset (TM/HM)",
        "Learnset (Move Tutor)",
        "Egg Moves",
        "Back to: All Pokémon",
        "Found an error?",
    }
    for line in lines[start + 1 :]:
        if line in section_headings:
            break
        result.append(line)
    return result


def parse_types(line: str) -> list[str]:
    value = line.removeprefix("Type").strip()
    if not value:
        return []
    tokens = value.split(" ")
    return [token for token in tokens if token in POKEMON_TYPES]


def parse_national_dex(lines: list[str]) -> int | None:
    index = find_line_index(lines, "National Dex")
    if index != -1 and index + 1 < len(lines):
        match = re.match(r"#?(\d+)", lines[index + 1])
        if match:
            return int(match.group(1))
    for line in lines:
        match = re.match(r"National Dex\s+#?(\d+)", line)
        if match:
            return int(match.group(1))
    return None


def parse_location(lines: list[str]) -> list[str]:
    start = find_line_index(lines, "Location")
    if start == -1:
        return []

    results: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("Abilities "):
            break
        if line == "Abilities":
            break
        if line.startswith("## "):
            break
        if line in {"Image", "Back to: All Pokémon"}:
            continue
        cleaned = line.removeprefix("• ").strip()
        if cleaned:
            results.append(cleaned)
    return results


def build_known_name_map(items: list[str]) -> list[tuple[str, str]]:
    pairs = [(item, normalize_name(item)) for item in items if item]
    return sorted(pairs, key=lambda pair: len(pair[1]), reverse=True)


def parse_abilities(
    lines: list[str],
    known_ability_names: list[tuple[str, str]],
) -> list[dict[str, str | None]]:
    abilities: list[dict[str, str | None]] = []
    start_index = find_line_index(lines, "Abilities")
    if start_index == -1:
        return abilities

    ability_lines: list[str] = []
    for line in lines[start_index + 1 :]:
        if line == "Egg Groups":
            break
        if line == "Wild Held Items":
            break
        if line in {
            "Evolution Line",
            "Moveset (Level Up)",
            "Learnset (TM/HM)",
            "Learnset (Move Tutor)",
            "Egg Moves",
        }:
            break
        ability_lines.append(line)

    index = 0
    while index < len(ability_lines):
        ability_name = ability_lines[index]
        effect = ability_lines[index + 1] if index + 1 < len(ability_lines) else None
        if ability_name != "-":
            abilities.append(
                {
                    "name": ability_name,
                    "effect": effect or None,
                }
            )
        index += 2
    return abilities


def parse_move_table(
    section_lines: list[str],
    *,
    source: str,
) -> list[ScrapedMoveEntry]:
    if not section_lines:
        return []

    moves: list[ScrapedMoveEntry] = []
    if section_lines and section_lines[0] in {"None.", "None"}:
        return []

    rows = section_lines[:]
    if source == "level-up":
        while rows and rows[0] in {"Lv.", "Move", "Type", "Cat", "Power", "Acc", "PP"}:
            rows.pop(0)
        stride = 6
        for index in range(0, len(rows), stride):
            chunk = rows[index : index + stride]
            if len(chunk) < stride:
                break
            level_match = re.match(r"(\d+)", chunk[0])
            if not level_match:
                continue
            moves.append(
                ScrapedMoveEntry(
                    move_name=chunk[1],
                    level=int(level_match.group(1)),
                    source=source,
                )
            )
    else:
        while rows and rows[0] in {"Move", "Type", "Cat", "Power", "Acc", "PP"}:
            rows.pop(0)
        stride = 5
        for index in range(0, len(rows), stride):
            chunk = rows[index : index + stride]
            if len(chunk) < stride:
                break
            moves.append(
                ScrapedMoveEntry(
                    move_name=chunk[0],
                    level=None,
                    source=source,
                )
            )
    return moves


def parse_acquire_method(acquire_text: str) -> tuple[str, int | None, str | None]:
    text = collapse_spaces(acquire_text)
    if text == "Base form":
        return "base", None, None

    level_match = re.match(r"Level\s+(\d+)(.*)$", text, re.I)
    if level_match:
        suffix = level_match.group(2).strip(" ,()")
        method = "level"
        if suffix:
            method = f"level-{normalize_name(suffix) or 'special'}"
        return method, int(level_match.group(1)), suffix or None

    if "Max Happiness" in text:
        if "Day" in text:
            return "friendship-day", None, text
        if "Night" in text:
            return "friendship-night", None, text
        return "friendship", None, text

    if "breed" in text.lower():
        return "breed", None, text

    if "trade" in text.lower():
        return "trade", None, text

    if "Stone" in text or "Apple" in text or "Scale" in text or "Whipped Dream" in text:
        return "item", None, text

    return normalize_name(text) or "other", None, text


def parse_evolution_section(
    section_lines: list[str],
    page_name: str,
) -> list[ScrapedEvolutionEntry]:
    if not section_lines or section_lines[0] in {"None.", "None"}:
        return []

    evolutions: list[ScrapedEvolutionEntry] = []
    rows = section_lines[:]
    while rows and rows[0] in {"Sprite", "Pokemon", "Pokémon", "Acquire At"}:
        rows.pop(0)

    last_species: str | None = None
    index = 0
    while index < len(rows):
        name = rows[index]

        if name.startswith("From ") and index + 2 < len(rows):
            source_name = name.removeprefix("From ").replace("→", "").strip()
            target_name = rows[index + 1]
            acquire = rows[index + 2]
            method, param, param_label = parse_acquire_method(acquire)
            if method != "base":
                evolutions.append(
                    ScrapedEvolutionEntry(
                        source_name=source_name,
                        target_name=target_name,
                        method=method,
                        param=param,
                        param_label=param_label,
                        raw_acquire=acquire,
                    )
                )
            last_species = target_name
            index += 3
            continue

        if index + 1 >= len(rows):
            break

        acquire = rows[index + 1]
        target_name = name.replace("From ", "").replace("→", "").strip()
        step = 2

        if acquire == "Baby form":
          last_species = target_name
          index += step
          if index < len(rows) and not rows[index].startswith("From "):
              index += 1
          continue

        if acquire == "Base form":
            if last_species is None:
                last_species = target_name
                index += step
                continue

            if index + 2 >= len(rows):
                last_species = target_name
                index += step
                continue

            acquire = rows[index + 2]
            step = 3

        source_name = last_species or page_name
        method, param, param_label = parse_acquire_method(acquire)
        if method != "base":
            evolutions.append(
                ScrapedEvolutionEntry(
                    source_name=source_name,
                    target_name=target_name,
                    method=method,
                    param=param,
                    param_label=param_label,
                    raw_acquire=acquire,
                )
            )
        last_species = target_name
        index += step

    return evolutions


def parse_page(html: str, page_url: str, known_ability_names: list[tuple[str, str]]) -> ScrapedPokemonPage | None:
    extractor = BlockTextExtractor()
    extractor.feed(html)
    lines = extractor.get_lines()

    page_name = ""
    for index, line in enumerate(lines):
        if line == "In: Pokédex" and index > 0:
            page_name = lines[index - 1]
            break
    if not page_name:
        h1_candidates = [line for line in lines if line and line not in {"Menu Close", "Pokémon Unbound"}]
        page_name = h1_candidates[0] if h1_candidates else ""
    if not page_name:
        return None

    types: list[str] = []
    type_index = find_line_index(lines, "Type")
    if type_index != -1 and type_index + 1 < len(lines):
        collected_types: list[str] = []
        for line in lines[type_index + 1 :]:
            if line == "National Dex":
                break
            if line in POKEMON_TYPES:
                collected_types.append(line)
            else:
                collected_types.extend(parse_types(line))
        types = collected_types

    return ScrapedPokemonPage(
        page_name=page_name,
        page_url=page_url,
        national_dex=parse_national_dex(lines),
        types=types,
        abilities=parse_abilities(lines, known_ability_names),
        locations=parse_location(lines),
        level_up_moves=parse_move_table(
            collect_section_lines(lines, "Moveset (Level Up)"),
            source="level-up",
        ),
        tm_moves=parse_move_table(
            collect_section_lines(lines, "Learnset (TM/HM)"),
            source="tm",
        ),
        tutor_moves=parse_move_table(
            collect_section_lines(lines, "Learnset (Move Tutor)"),
            source="tutor",
        ),
        egg_moves=parse_move_table(
            collect_section_lines(lines, "Egg Moves"),
            source="egg",
        ),
        evolutions=parse_evolution_section(
            collect_section_lines(lines, "Evolution Line"),
            page_name,
        ),
    )


def build_name_maps(
    species: list[dict[str, Any]],
    abilities: list[dict[str, Any]],
    moves: list[dict[str, Any]],
) -> dict[str, Any]:
    species_by_normalized_name: dict[str, list[dict[str, Any]]] = {}
    species_by_national_dex: dict[int, list[dict[str, Any]]] = {}
    for row in species:
        species_by_normalized_name.setdefault(normalize_name(row["name"]), []).append(row)
        display_name = row.get("displayName")
        if isinstance(display_name, str) and display_name:
            species_by_normalized_name.setdefault(normalize_name(display_name), []).append(row)
        national_dex = row.get("sourceNationalDex")
        if isinstance(national_dex, int):
            species_by_national_dex.setdefault(national_dex, []).append(row)

    for normalized_name, rows in species_by_normalized_name.items():
        species_by_normalized_name[normalized_name] = sorted(
            rows,
            key=lambda row: row["speciesId"],
        )

    ability_by_normalized_name = {
        normalize_name(row["name"]): row for row in abilities if row.get("name")
    }
    move_by_normalized_name = {
        normalize_name(row["name"]): row for row in moves if row.get("name")
    }

    return {
        "speciesByName": species_by_normalized_name,
        "speciesByDex": species_by_national_dex,
        "abilityByName": ability_by_normalized_name,
        "moveByName": move_by_normalized_name,
    }


def attach_national_dex(species: list[dict[str, Any]]) -> None:
    for row in species:
        row.setdefault("sourceNationalDex", None)


def match_species_row(
    name: str,
    national_dex: int | None,
    name_maps: dict[str, Any],
    *,
    page_types: list[str] | None = None,
    page_abilities: list[dict[str, str | None]] | None = None,
) -> dict[str, Any] | None:
    direct_candidates = name_maps["speciesByName"].get(normalize_name(name), [])
    if direct_candidates:
        return choose_best_species_row(
            direct_candidates,
            requested_name=name,
            national_dex=national_dex,
            page_types=page_types,
            page_abilities=page_abilities,
        )

    _, base_name = split_variant_name(name)
    base_candidates = name_maps["speciesByName"].get(normalize_name(base_name), [])
    if base_candidates:
        return choose_best_species_row(
            base_candidates,
            requested_name=name,
            national_dex=national_dex,
            page_types=page_types,
            page_abilities=page_abilities,
        )

    if national_dex is not None:
        candidates = name_maps["speciesByDex"].get(national_dex, [])
        if candidates:
            return choose_best_species_row(
                candidates,
                requested_name=name,
                national_dex=national_dex,
                page_types=page_types,
                page_abilities=page_abilities,
            )
    return None


def merge_species_data(
    species: list[dict[str, Any]],
    abilities: list[dict[str, Any]],
    moves: list[dict[str, Any]],
    scraped_pages: list[ScrapedPokemonPage],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    name_maps = build_name_maps(species, abilities, moves)
    ability_effects: dict[int, str] = {}
    evolution_map: dict[int, list[dict[str, Any]]] = {}
    level_up_map: dict[int, list[dict[str, Any]]] = {}
    tm_map: dict[int, list[dict[str, Any]]] = {}
    tutor_map: dict[int, list[dict[str, Any]]] = {}
    egg_map: dict[int, list[dict[str, Any]]] = {}
    research_species = load_research_species()
    page_species_rows: dict[str, dict[str, Any]] = {}
    next_synthetic_species_id = max(row["speciesId"] for row in species) + 1

    def create_supplemental_species_row(page: ScrapedPokemonPage) -> dict[str, Any] | None:
        nonlocal next_synthetic_species_id

        variant_prefix, base_name = split_variant_name(page.page_name)
        if variant_prefix is None:
            return None

        research_candidates = [
            row
            for row in research_species
            if normalize_name(row.get("name", "")) == normalize_name(base_name)
        ]
        research_row = choose_best_species_row(
            research_candidates,
            national_dex=page.national_dex,
            page_types=page.types,
            page_abilities=page.abilities,
        )
        if not research_row:
            return None

        species_row = {
            "speciesId": next_synthetic_species_id,
            "name": page.page_name,
            "baseStats": research_row.get("baseStats", {}),
            "types": page.types[:2] if page.types else research_row.get("types", []),
            "catchRate": research_row.get("catchRate", 0),
            "expYield": research_row.get("expYield", 0),
            "evYield": research_row.get("evYield", {}),
            "heldItem1Id": research_row.get("heldItem1Id", 0),
            "heldItem1Name": research_row.get("heldItem1Name"),
            "heldItem2Id": research_row.get("heldItem2Id", 0),
            "heldItem2Name": research_row.get("heldItem2Name"),
            "genderRatio": research_row.get("genderRatio", 0),
            "eggCycles": research_row.get("eggCycles", 0),
            "friendship": research_row.get("friendship", 0),
            "growthRateToken": research_row.get("growthRateToken"),
            "eggGroup1Token": research_row.get("eggGroup1Token"),
            "eggGroup2Token": research_row.get("eggGroup2Token"),
            "ability1Id": research_row.get("ability1Id", 0),
            "ability1Name": research_row.get("ability1Name"),
            "ability2Id": research_row.get("ability2Id", 0),
            "ability2Name": research_row.get("ability2Name"),
            "hiddenAbilityId": research_row.get("hiddenAbilityId", 0),
            "hiddenAbilityName": research_row.get("hiddenAbilityName"),
            "safariFleeRate": research_row.get("safariFleeRate", 0),
            "noFlip": research_row.get("noFlip", False),
            "sourceNationalDex": page.national_dex,
            "source": {
                "kind": "research-supplement",
                "primary": "unboundwiki.com",
                "fallback": "research/unbound-bundle/decoded/species.json",
                "wikiPage": page.page_url,
            },
        }
        next_synthetic_species_id += 1
        species.append(species_row)
        return species_row

    for page in sorted(scraped_pages, key=lambda entry: entry.page_url):
        variant_prefix, base_name = split_variant_name(page.page_name)
        exact_variant_candidates = name_maps["speciesByName"].get(
            normalize_name(page.page_name),
            [],
        )
        base_candidates = name_maps["speciesByName"].get(
            normalize_name(base_name),
            [],
        )

        if variant_prefix and not exact_variant_candidates and len(base_candidates) <= 1:
            species_row = None
        else:
            species_row = match_species_row(
                page.page_name,
                page.national_dex,
                name_maps,
                page_types=page.types,
                page_abilities=page.abilities,
            )
        if not species_row:
            species_row = create_supplemental_species_row(page)
            if species_row:
                name_maps = build_name_maps(species, abilities, moves)
        if not species_row:
            continue

        if page.page_name != species_row["name"]:
            species_row["displayName"] = page.page_name
        if page.national_dex is not None:
            species_row["sourceNationalDex"] = page.national_dex
        if page.types:
            if len(page.types) == 1:
                species_row["types"] = [page.types[0], page.types[0]]
            else:
                species_row["types"] = page.types[:2]
        if page.locations:
            species_row["locations"] = page.locations
            species_row["locationSummary"] = " / ".join(page.locations)
        species_row["wikiPage"] = page.page_url
        species_row["source"] = {
            "kind": "merged-source",
            "primary": "unboundwiki.com",
            "fallback": "Skeli789 source repositories",
            "wikiPage": page.page_url,
        }
        page_species_rows[page.page_url] = species_row

        scraped_abilities = page.abilities[:3]
        available_slots = [("ability1Id", "ability1Name")]
        if species_row.get("ability2Id"):
            available_slots.append(("ability2Id", "ability2Name"))
        if species_row.get("hiddenAbilityId"):
            available_slots.append(("hiddenAbilityId", "hiddenAbilityName"))
        if len(scraped_abilities) > len(available_slots):
            available_slots = [
                ("ability1Id", "ability1Name"),
                ("ability2Id", "ability2Name"),
                ("hiddenAbilityId", "hiddenAbilityName"),
            ]

        touched_slots: set[str] = set()
        for scraped_ability, (id_key, name_key) in zip(scraped_abilities, available_slots):
            touched_slots.add(id_key)
            ability_row = name_maps["abilityByName"].get(normalize_name(scraped_ability["name"] or ""))
            if ability_row:
                species_row[id_key] = ability_row["abilityId"]
                species_row[name_key] = ability_row["name"]
                effect = scraped_ability.get("effect")
                if effect:
                    ability_effects[ability_row["abilityId"]] = effect
            else:
                species_row[name_key] = scraped_ability["name"]

        for id_key, name_key in (
            ("ability2Id", "ability2Name"),
            ("hiddenAbilityId", "hiddenAbilityName"),
        ):
            if id_key in touched_slots:
                continue
            if (id_key, name_key) not in available_slots:
                species_row[id_key] = 0
                species_row[name_key] = None

    name_maps = build_name_maps(species, abilities, moves)

    for page in sorted(scraped_pages, key=lambda entry: entry.page_url):
        species_row = page_species_rows.get(page.page_url)

        for move_list, target_map in (
            (page.level_up_moves, level_up_map),
            (page.tm_moves, tm_map),
            (page.tutor_moves, tutor_map),
            (page.egg_moves, egg_map),
        ):
            if not species_row:
                continue
            entries: list[dict[str, Any]] = []
            for move_entry in move_list:
                move_row = name_maps["moveByName"].get(normalize_name(move_entry.move_name))
                if not move_row:
                    continue
                payload = {
                    "moveId": move_row["moveId"],
                    "moveName": move_row["name"],
                    "source": move_entry.source,
                }
                if move_entry.level is not None:
                    payload["level"] = move_entry.level
                entries.append(payload)
            target_map[species_row["speciesId"]] = entries

        for evolution in page.evolutions:
            source_row = match_species_row(evolution.source_name, None, name_maps)
            target_row = match_species_row(evolution.target_name, None, name_maps)
            if not source_row or not target_row:
                continue
            if not should_export_evolution_edge(
                source_row["speciesId"],
                target_row["speciesId"],
                evolution.method,
            ):
                continue
            evolution_map.setdefault(source_row["speciesId"], [])
            evolution_map[source_row["speciesId"]].append(
                {
                    "method": evolution.method,
                    "param": evolution.param,
                    "paramLabel": evolution.param_label,
                    "targetSpeciesId": target_row["speciesId"],
                    "targetSpeciesName": target_row.get("displayName", target_row["name"]),
                    "source": {
                        "kind": "wiki-page",
                        "page": page.page_url,
                        "rawAcquire": evolution.raw_acquire,
                    },
                }
            )

    merged_abilities: list[dict[str, Any]] = []
    for row in abilities:
        updated = dict(row)
        if row["abilityId"] in ability_effects:
            updated["effect"] = ability_effects[row["abilityId"]]
        merged_abilities.append(updated)

    def build_learnset_rows(
        per_species_moves: dict[int, list[dict[str, Any]]],
        learnset_source: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for species_row in species:
            species_id = species_row["speciesId"]
            if species_id not in per_species_moves:
                continue
            moves_payload = per_species_moves[species_id]
            deduped: list[dict[str, Any]] = []
            seen: set[tuple[Any, ...]] = set()
            for move in moves_payload:
                key = (move["moveId"], move.get("level"), move.get("slot"))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(move)
            if learnset_source == "level-up":
                deduped.sort(key=lambda move: (move.get("level", 0), move["moveId"]))
            else:
                deduped.sort(key=lambda move: move["moveId"])
            rows.append(
                {
                    "speciesId": species_id,
                    "speciesName": get_species_label(species_row),
                    "moves": deduped,
                    "source": {
                        "kind": "wiki-page",
                        "base": "https://unboundwiki.com/pokemon/",
                        "learnsetType": learnset_source,
                    },
                }
            )
        return rows

    merged_evolutions: list[dict[str, Any]] = []
    for species_row in species:
        species_id = species_row["speciesId"]
        if species_id not in evolution_map:
            continue
        deduped_evolutions: list[dict[str, Any]] = []
        seen_edges: set[tuple[Any, ...]] = set()
        for evolution in evolution_map[species_id]:
            canonical_label = canonicalize_evolution_text(evolution["paramLabel"])
            canonical_method = canonicalize_evolution_text(evolution["method"])
            key = (
                evolution["targetSpeciesId"],
                evolution["param"],
                canonical_label or canonical_method,
                "item" if canonical_method == "item" else None,
            )
            if key in seen_edges:
                continue
            seen_edges.add(key)
            deduped_evolutions.append(evolution)
        merged_evolutions.append(
            {
                "speciesId": species_id,
                "speciesName": get_species_label(species_row),
                "evolutions": deduped_evolutions,
                "source": {
                    "kind": "wiki-pages",
                    "base": "https://unboundwiki.com/pokemon/",
                },
            }
        )

    level_up = build_learnset_rows(level_up_map, "level-up")
    tm = build_learnset_rows(tm_map, "tm")
    tutor = build_learnset_rows(tutor_map, "tutor")
    egg = build_learnset_rows(egg_map, "egg")
    return species, merged_abilities, merged_evolutions, level_up, tm, tutor, egg


def merge_source_and_scraped() -> dict[str, Any]:
    indexes = source_data.load_indexes()

    species = source_data.parse_base_stats(indexes)
    moves = source_data.parse_moves(indexes)
    abilities = [
        {"abilityId": ability_id, "name": name}
        for ability_id, name in enumerate(indexes["abilityNames"])
    ]
    attach_national_dex(species)

    index_html = fetch_text(INDEX_URL, cache_key="pokemon-index.html")
    pokemon_urls = collect_pokemon_urls(index_html)
    ability_name_pairs = build_known_name_map([row["name"] for row in abilities])

    scraped_pages: list[ScrapedPokemonPage] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(
                fetch_text,
                url,
                cache_key=f"{url.rstrip('/').split('/')[-1]}.html",
            ): url
            for url in pokemon_urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            html = future.result()
            page = parse_page(html, url, ability_name_pairs)
            if page:
                scraped_pages.append(page)

    species, abilities, evolutions, level_up, tm, tutor, egg = merge_species_data(
        species,
        abilities,
        moves,
        scraped_pages,
    )
    combined = source_data.combine_learnsets(level_up, egg, tm, tutor)
    items = source_data.parse_referenced_items(species, evolutions)
    summary = {
        "source": {
            "primaryDataset": "Pokémon Unbound Wiki",
            "primaryUrl": "https://unboundwiki.com/pokemon/",
            "fallbackDataset": "Skeli789 source repositories",
            "generatedAt": time.strftime("%Y-%m-%d"),
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
                "status": "wiki-merged",
                "count": len(species),
                "notes": [
                    "Types, ability slots, and locations are refreshed from unboundwiki.com where a matching page exists.",
                    "Base stats and canonical numeric IDs remain sourced from the local DPE/CFRU tables.",
                ],
            },
            "abilities": {
                "status": "wiki-merged",
                "count": len(abilities),
                "notes": [
                    "Ability effect text is aggregated from per-Pokémon wiki pages.",
                ],
            },
            "evolutions": {
                "status": "wiki-scraped",
                "count": sum(len(entry["evolutions"]) for entry in evolutions),
                "notes": [
                    "Evolution chains and acquire conditions are scraped from each wiki Pokémon page.",
                ],
            },
            "learnsetsLevel": {
                "status": "wiki-scraped",
                "count": len(level_up),
            },
            "learnsetsEgg": {
                "status": "wiki-scraped",
                "count": len(egg),
            },
            "learnsetsTmHm": {
                "status": "wiki-scraped",
                "count": len(tm),
            },
            "learnsetsTutor": {
                "status": "wiki-scraped",
                "count": len(tutor),
            },
            "learnsetsCombined": {
                "status": "wiki-scraped",
                "count": len(combined),
            },
        },
    }

    return {
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


def main() -> None:
    outputs = merge_source_and_scraped()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in outputs.items():
        write_json(OUTPUT_DIR / filename, payload)
    print(f"Wrote wiki-backed extracted data to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
