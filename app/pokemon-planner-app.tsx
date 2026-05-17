"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  DAMAGE_FILTERS,
  type DamageFilter,
  type LearnableMove,
  type Move,
  type MoveCategory,
  type PokemonType,
  type Stats,
  calculateMoveDamage,
  formatMultiplier,
  getMoveEffectivenessColor,
  getTypeEffectiveness,
  inferStatlineTotal,
} from "@/lib/battle";
import { parsePokemonUnboundSave, type ParsedSaveFile } from "@/lib/save";

type ExtractedSpeciesRecord = {
  speciesId: number;
  name: string;
  baseStats: Stats;
  types: PokemonType[];
};

type ExtractedMoveRecord = {
  moveId: number;
  name: string;
  power: number;
  typeName: PokemonType;
  categoryName: MoveCategory;
};

type ExtractedCombinedLearnset = {
  speciesId: number;
  speciesName: string;
  moves: Array<{
    level?: number;
    slot?: number;
    moveId: number;
    moveName: string | null;
    source: "level-up" | "egg" | "tm" | "tutor";
  }>;
};

type ExtractedEvolutionRecord = {
  speciesId: number;
  speciesName: string;
  evolutions: Array<{
    method: string;
    param: number | null;
    paramLabel: string | null;
    targetSpeciesId: number;
    targetSpeciesName: string;
  }>;
};

type ItemRecord = {
  itemId: number;
  name: string;
};

type ScrapedGymLeaderSet = {
  source: string;
  gyms: ScrapedGymEntry[];
};

type ScrapedGymEntry = {
  gymNumber: number;
  location: string;
  leader: string;
  badge: string;
  gymType: PokemonType;
  difficulties: ScrapedGymDifficulty[];
};

type ScrapedGymDifficulty = {
  battleType: string;
  difficulty: string;
  team: ScrapedGymPokemon[];
};

type ScrapedGymPokemon = {
  gender: string | null;
  nationalDex: number | null;
  ability: string | null;
  evSpread: string | null;
  form: string | null;
  heldItem: string | null;
  level: number | null;
  moves: Array<{
    category: "Physical" | "Special" | "Status";
    name: string;
    type: PokemonType;
  }>;
  nature: string | null;
  pokemon: string;
  types: PokemonType[];
};

type GymTeamMember = {
  ability: string | null;
  baseStats: Stats;
  evSpread: string | null;
  gender: string | null;
  heldItem: string | null;
  id: string;
  level: number;
  moveSummaries: Array<Move & { multiplier: number }>;
  name: string;
  nature: string | null;
  nationalDex: number | null;
  types: PokemonType[];
};

type CandidateMove = LearnableMove & {
  detailLabel: string;
};

type RosterCandidate = {
  currentMoves: Move[];
  currentMoveSummary: string;
  currentSpeciesName: string;
  displayName: string;
  heldItemName: string | null;
  key: string;
  learnset: CandidateMove[];
  level: number;
  locationLabel: string;
  methodLabel: string | null;
  nature: string;
  speciesId: number;
  speciesName: string;
  stats: Stats;
  types: PokemonType[];
};

type CompareSlotId = "left" | "right";

type LoadedDatasets = {
  combinedLearnsets: ExtractedCombinedLearnset[];
  evolutions: ExtractedEvolutionRecord[];
  gymLeaders: ScrapedGymLeaderSet;
  items: ItemRecord[];
  moves: ExtractedMoveRecord[];
  species: ExtractedSpeciesRecord[];
};

const EMPTY_STATS: Stats = {
  hp: 0,
  atk: 0,
  def: 0,
  spa: 0,
  spd: 0,
  spe: 0,
};

const TYPE_OPTIONS: Array<PokemonType | "All"> = [
  "All",
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
];

function toMoveCategory(
  category: "Physical" | "Special" | "Status",
): MoveCategory {
  if (category === "Physical") {
    return "physical";
  }

  if (category === "Special") {
    return "special";
  }

  return "status";
}

function formatMoveSource(move: ExtractedCombinedLearnset["moves"][number]) {
  if (move.source === "level-up") {
    return `Lv ${move.level ?? 1}`;
  }

  if (move.source === "tm") {
    return `TM/HM ${move.slot ?? "?"}`;
  }

  if (move.source === "tutor") {
    return `Tutor ${move.slot ?? "?"}`;
  }

  return "Egg";
}

function moveMatchesFilter(
  move: Pick<LearnableMove, "type">,
  defendingTypes: PokemonType[],
  filter: DamageFilter,
) {
  const multiplier = getTypeEffectiveness(move.type, defendingTypes);

  if (filter === "super") {
    return multiplier >= 2;
  }

  if (filter === "neutral") {
    return multiplier === 1;
  }

  return multiplier > 0 && multiplier <= 0.5;
}

function canShowEvolutionUnderCap(
  evolution: ExtractedEvolutionRecord["evolutions"][number],
  currentLevel: number,
  levelCap: number,
) {
  if (evolution.method.includes("trade")) {
    return false;
  }

  if (evolution.method.startsWith("level")) {
    return typeof evolution.param === "number" && evolution.param <= levelCap;
  }

  if (evolution.method === "none") {
    return false;
  }

  return currentLevel <= levelCap;
}

function formatEvolutionMethod(
  evolution: ExtractedEvolutionRecord["evolutions"][number],
) {
  if (evolution.method.startsWith("level")) {
    return `Evolves by Lv ${evolution.param ?? "?"}`;
  }

  if (evolution.paramLabel) {
    return `Evolves via ${evolution.paramLabel}`;
  }

  return `Evolves via ${evolution.method.replaceAll("-", " ")}`;
}

function getPortraitLabel(speciesName: string) {
  return speciesName
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
}

function getNatureSummary(nature: string | null) {
  const natureMap: Record<string, { up: string; down: string }> = {
    Adamant: { up: "Atk", down: "SpA" },
    Bashful: { up: "None", down: "None" },
    Bold: { up: "Def", down: "Atk" },
    Brave: { up: "Atk", down: "Spe" },
    Calm: { up: "SpD", down: "Atk" },
    Careful: { up: "SpD", down: "SpA" },
    Docile: { up: "None", down: "None" },
    Gentle: { up: "SpD", down: "Def" },
    Hardy: { up: "None", down: "None" },
    Hasty: { up: "Spe", down: "Def" },
    Impish: { up: "Def", down: "SpA" },
    Jolly: { up: "Spe", down: "SpA" },
    Lax: { up: "Def", down: "SpD" },
    Lonely: { up: "Atk", down: "Def" },
    Mild: { up: "SpA", down: "Def" },
    Modest: { up: "SpA", down: "Atk" },
    Naive: { up: "Spe", down: "SpD" },
    Naughty: { up: "Atk", down: "SpD" },
    Quiet: { up: "SpA", down: "Spe" },
    Quirky: { up: "None", down: "None" },
    Rash: { up: "SpA", down: "SpD" },
    Relaxed: { up: "Def", down: "Spe" },
    Sassy: { up: "SpD", down: "Spe" },
    Serious: { up: "None", down: "None" },
    Timid: { up: "Spe", down: "Atk" },
  };

  if (!nature) {
    return "Unknown nature";
  }

  const summary = natureMap[nature];
  if (!summary || summary.up === "None") {
    return nature;
  }

  return `${nature} (+${summary.up}, -${summary.down})`;
}

function getTypeColor(type: PokemonType) {
  const colors: Record<PokemonType, string> = {
    Normal: "#9FA19F",
    Fire: "#E62829",
    Water: "#2980EF",
    Electric: "#FAC000",
    Grass: "#3FA129",
    Ice: "#3FD8FF",
    Fighting: "#FF8000",
    Poison: "#9141CB",
    Ground: "#915121",
    Flying: "#81B9EF",
    Psychic: "#EF4179",
    Bug: "#91A119",
    Rock: "#AFA981",
    Ghost: "#704170",
    Dragon: "#5060E1",
    Dark: "#624D4E",
    Steel: "#60A1B8",
    Fairy: "#EF70EF",
  };

  return colors[type];
}

function getCategoryColor(category: MoveCategory) {
  if (category === "physical") {
    return "#EB5628";
  }

  if (category === "special") {
    return "#3E6978";
  }

  return "#676967";
}

function getSpriteUrl(pokemon: GymTeamMember) {
  if (!pokemon.nationalDex) {
    return null;
  }

  return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/${pokemon.nationalDex}.png`;
}

function getStatBarColor(value: number) {
  if (value >= 100) {
    return "bg-green-500";
  }

  if (value >= 80) {
    return "bg-yellow-500";
  }

  return "bg-rose-500";
}

function formatStatLabel(stat: keyof Stats) {
  if (stat === "atk") {
    return "Attack";
  }

  if (stat === "def") {
    return "Defense";
  }

  if (stat === "spa") {
    return "Sp. Atk";
  }

  if (stat === "spd") {
    return "Sp. Def";
  }

  if (stat === "spe") {
    return "Speed";
  }

  return "HP";
}

function prettyFileSize(bytes: number) {
  return `${Math.round(bytes / 1024)} KB`;
}

function buildMoveSummary(moves: Move[]) {
  if (moves.length === 0) {
    return "No moves recorded";
  }

  return moves.map((move) => move.name).join(", ");
}

function StatBlock({ stats }: { stats: Stats }) {
  return (
    <div className="flex flex-col justify-center rounded-[22px] border border-[rgba(29,35,48,0.12)] bg-[rgba(255,248,231,0.72)] p-4">
      <div className="mb-5 flex items-center gap-2 text-[var(--accent)]">
        <svg
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
          />
        </svg>
        <span className="text-sm font-semibold uppercase tracking-[0.12em]">
          Base Stats
        </span>
      </div>
      <div className="space-y-4">
        {(Object.entries(stats) as Array<[keyof Stats, number]>).map(
          ([stat, value]) => {
            const width = `${Math.min(100, (value / 255) * 100)}%`;

            return (
              <div className="flex items-center gap-3 text-sm" key={stat}>
                <span className="w-20 shrink-0 text-right text-[0.72rem] font-bold uppercase tracking-wider text-slate-500">
                  {formatStatLabel(stat)}
                </span>
                <span className="w-8 shrink-0 text-right font-mono font-bold text-slate-800">
                  {value}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200 shadow-inner">
                  <div
                    className={`h-full rounded-full ${getStatBarColor(value)}`}
                    style={{ width }}
                  />
                </div>
              </div>
            );
          },
        )}
      </div>
    </div>
  );
}

export function PokemonPlannerApp() {
  const [datasets, setDatasets] = useState<LoadedDatasets | null>(null);
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveFileName, setSaveFileName] = useState("");
  const [saveData, setSaveData] = useState<ParsedSaveFile | null>(null);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [typeFilter, setTypeFilter] = useState<PokemonType | "All">("All");
  const [showEvolutions, setShowEvolutions] = useState(true);
  const [selectedGymLeader, setSelectedGymLeader] = useState("");
  const [selectedDifficulty, setSelectedDifficulty] = useState("");
  const [selectedEnemyId, setSelectedEnemyId] = useState("");
  const [manualLevelCap, setManualLevelCap] = useState("");
  const [damageFilter, setDamageFilter] = useState<DamageFilter>("super");
  const [leftCandidateKey, setLeftCandidateKey] = useState<string | null>(null);
  const [rightCandidateKey, setRightCandidateKey] = useState<string | null>(
    null,
  );
  const [activeCompareSlot, setActiveCompareSlot] =
    useState<CompareSlotId>("left");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [
          speciesResponse,
          movesResponse,
          learnsetsResponse,
          evolutionsResponse,
          gymsResponse,
          itemsResponse,
        ] = await Promise.all([
          fetch("/extracted/species.json"),
          fetch("/extracted/moves.json"),
          fetch("/extracted/learnsets-combined.json"),
          fetch("/extracted/evolutions.json"),
          fetch("/extracted/gym-leaders.json"),
          fetch("/extracted/items-partial.json"),
        ]);

        const nextDatasets: LoadedDatasets = {
          combinedLearnsets:
            (await learnsetsResponse.json()) as ExtractedCombinedLearnset[],
          evolutions:
            (await evolutionsResponse.json()) as ExtractedEvolutionRecord[],
          gymLeaders: (await gymsResponse.json()) as ScrapedGymLeaderSet,
          items: (await itemsResponse.json()) as ItemRecord[],
          moves: (await movesResponse.json()) as ExtractedMoveRecord[],
          species: (await speciesResponse.json()) as ExtractedSpeciesRecord[],
        };

        if (!cancelled) {
          setDatasets(nextDatasets);
          setLoadError("");
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            error instanceof Error
              ? error.message
              : "Failed to load extracted Unbound data.",
          );
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const speciesById = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.species ?? []).map((species) => [
          species.speciesId,
          species,
        ]),
      ) as Record<number, ExtractedSpeciesRecord>,
    [datasets],
  );

  const speciesByName = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.species ?? []).map((species) => [species.name, species]),
      ) as Record<string, ExtractedSpeciesRecord>,
    [datasets],
  );

  const moveById = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.moves ?? []).map((move) => [move.moveId, move]),
      ) as Record<number, ExtractedMoveRecord>,
    [datasets],
  );

  const moveByName = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.moves ?? []).map((move) => [move.name, move]),
      ) as Record<string, ExtractedMoveRecord>,
    [datasets],
  );

  const combinedLearnsetBySpeciesId = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.combinedLearnsets ?? []).map((learnset) => [
          learnset.speciesId,
          learnset,
        ]),
      ) as Record<number, ExtractedCombinedLearnset>,
    [datasets],
  );

  const evolutionsBySpeciesId = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.evolutions ?? []).map((evolution) => [
          evolution.speciesId,
          evolution,
        ]),
      ) as Record<number, ExtractedEvolutionRecord>,
    [datasets],
  );

  const itemById = useMemo(
    () =>
      Object.fromEntries(
        (datasets?.items ?? []).map((item) => [item.itemId, item.name]),
      ) as Record<number, string>,
    [datasets],
  );

  const availableGyms = datasets?.gymLeaders.gyms ?? [];
  const effectiveSelectedGymLeader = availableGyms.some(
    (gym) => gym.leader === selectedGymLeader,
  )
    ? selectedGymLeader
    : (availableGyms[0]?.leader ?? "");
  const selectedGym =
    availableGyms.find((gym) => gym.leader === effectiveSelectedGymLeader) ??
    null;
  const availableDifficulties = selectedGym?.difficulties ?? [];
  const effectiveSelectedDifficulty = availableDifficulties.some(
    (difficulty) => difficulty.difficulty === selectedDifficulty,
  )
    ? selectedDifficulty
    : (availableDifficulties[0]?.difficulty ?? "");

  const selectedGymDifficulty =
    availableDifficulties.find(
      (difficulty) => difficulty.difficulty === effectiveSelectedDifficulty,
    ) ?? null;
  const gymTeam =
    selectedGym && selectedGymDifficulty
      ? selectedGymDifficulty.team.map((pokemon, index) => {
          const species = speciesByName[pokemon.pokemon];
          return {
            ability: pokemon.ability,
            baseStats: species?.baseStats ?? EMPTY_STATS,
            evSpread: pokemon.evSpread,
            gender: pokemon.gender,
            heldItem: pokemon.heldItem,
            id: `${selectedGym.leader}-${selectedGymDifficulty.difficulty}-${index}`,
            level: pokemon.level ?? 1,
            moveSummaries: pokemon.moves.map((move) => {
              const extractedMove = moveByName[move.name];
              return {
                category:
                  extractedMove?.categoryName ?? toMoveCategory(move.category),
                multiplier: 1,
                name: move.name,
                power: extractedMove?.power ?? 0,
                type: extractedMove?.typeName ?? move.type,
              };
            }),
            name: pokemon.form
              ? `${pokemon.pokemon}${pokemon.form}`
              : pokemon.pokemon,
            nature: pokemon.nature,
            nationalDex: pokemon.nationalDex,
            types: species?.types ?? pokemon.types,
          } satisfies GymTeamMember;
        })
      : [];

  const defaultLevelCap =
    gymTeam.length > 0
      ? Math.max(...gymTeam.map((pokemon) => pokemon.level))
      : 1;

  const levelCap = useMemo(() => {
    const parsed = Number.parseInt(manualLevelCap, 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed;
    }

    return defaultLevelCap;
  }, [defaultLevelCap, manualLevelCap]);

  const baseRoster = useMemo(() => {
    if (!saveData) {
      return [];
    }

    const roster: RosterCandidate[] = [];

    for (const pokemon of saveData.pokemon) {
      const species = speciesById[pokemon.speciesId];
      if (!species) {
        continue;
      }

      const learnset =
        combinedLearnsetBySpeciesId[pokemon.speciesId]?.moves
          .map((move) => {
            const extractedMove = moveById[move.moveId];
            if (!extractedMove) {
              return null;
            }

            return {
              category: extractedMove.categoryName,
              detailLabel: formatMoveSource(move),
              name: extractedMove.name,
              power: extractedMove.power,
              source: move.source,
              type: extractedMove.typeName,
            } satisfies CandidateMove;
          })
          .filter((move): move is CandidateMove => move !== null) ?? [];

      const currentMoves = pokemon.moveIds
        .map((moveId) => moveById[moveId])
        .filter((move): move is ExtractedMoveRecord => Boolean(move))
        .map((move) => ({
          category: move.categoryName,
          name: move.name,
          power: move.power,
          type: move.typeName,
        }));

      roster.push({
        currentMoves,
        currentMoveSummary: buildMoveSummary(currentMoves),
        currentSpeciesName: species.name,
        displayName: pokemon.nickname
          ? `${pokemon.nickname} (${species.name})`
          : species.name,
        heldItemName: itemById[pokemon.heldItemId] ?? null,
        key: pokemon.isParty
          ? `party:${pokemon.slotIndex}:${pokemon.speciesId}`
          : `box:${pokemon.boxIndex}:${pokemon.slotIndex}:${pokemon.speciesId}`,
        learnset,
        level: pokemon.level,
        locationLabel: pokemon.isParty
          ? `Party slot ${pokemon.slotIndex + 1}`
          : `Box ${(pokemon.boxIndex ?? 0) + 1}, Slot ${pokemon.slotIndex + 1}`,
        methodLabel: null,
        nature: pokemon.nature,
        speciesId: pokemon.speciesId,
        speciesName: species.name,
        stats: species.baseStats,
        types: species.types,
      });
    }

    return roster;
  }, [combinedLearnsetBySpeciesId, itemById, moveById, saveData, speciesById]);

  const searchCandidates = useMemo(() => {
    const candidates: RosterCandidate[] = [...baseRoster];

    if (!showEvolutions) {
      return candidates;
    }

    for (const candidate of baseRoster) {
      const evolutionRecord = evolutionsBySpeciesId[candidate.speciesId];
      if (!evolutionRecord) {
        continue;
      }

      for (const evolution of evolutionRecord.evolutions) {
        if (!canShowEvolutionUnderCap(evolution, candidate.level, levelCap)) {
          continue;
        }

        const evolvedSpecies = speciesById[evolution.targetSpeciesId];
        if (!evolvedSpecies) {
          continue;
        }

        const evolvedLearnset =
          combinedLearnsetBySpeciesId[evolution.targetSpeciesId]?.moves
            .map((move) => {
              const extractedMove = moveById[move.moveId];
              if (!extractedMove) {
                return null;
              }

              return {
                category: extractedMove.categoryName,
                detailLabel: formatMoveSource(move),
                name: extractedMove.name,
                power: extractedMove.power,
                source: move.source,
                type: extractedMove.typeName,
              } satisfies CandidateMove;
            })
            .filter((move): move is CandidateMove => move !== null) ?? [];

        candidates.push({
          ...candidate,
          displayName: `${evolvedSpecies.name} (${candidate.displayName})`,
          key: `${candidate.key}:evo:${evolution.targetSpeciesId}:${evolution.method}:${evolution.param ?? "na"}`,
          learnset: evolvedLearnset,
          methodLabel: formatEvolutionMethod(evolution),
          speciesId: evolvedSpecies.speciesId,
          speciesName: evolvedSpecies.name,
          stats: evolvedSpecies.baseStats,
          types: evolvedSpecies.types,
        });
      }
    }

    return candidates;
  }, [
    baseRoster,
    combinedLearnsetBySpeciesId,
    evolutionsBySpeciesId,
    levelCap,
    moveById,
    showEvolutions,
    speciesById,
  ]);

  const normalizedSearch = deferredSearch.trim().toLowerCase();
  const filteredCandidates = useMemo(
    () =>
      searchCandidates.filter((candidate) => {
        const matchesSearch =
          normalizedSearch.length === 0 ||
          candidate.displayName.toLowerCase().includes(normalizedSearch) ||
          candidate.speciesName.toLowerCase().includes(normalizedSearch) ||
          candidate.types.some((type) =>
            type.toLowerCase().includes(normalizedSearch),
          );
        const matchesType =
          typeFilter === "All" || candidate.types.includes(typeFilter);
        return matchesSearch && matchesType;
      }),
    [normalizedSearch, searchCandidates, typeFilter],
  );

  const candidateByKey = useMemo(
    () =>
      Object.fromEntries(
        searchCandidates.map((candidate) => [candidate.key, candidate]),
      ) as Record<string, RosterCandidate>,
    [searchCandidates],
  );

  const effectiveLeftCandidateKey =
    leftCandidateKey && candidateByKey[leftCandidateKey]
      ? leftCandidateKey
      : (baseRoster[0]?.key ?? null);
  const effectiveRightCandidateKey =
    rightCandidateKey && candidateByKey[rightCandidateKey]
      ? rightCandidateKey
      : (baseRoster[1]?.key ?? baseRoster[0]?.key ?? null);
  const selectedEnemy =
    gymTeam.find((pokemon) => pokemon.id === selectedEnemyId) ??
    gymTeam[0] ??
    null;
  const leftCandidate =
    (effectiveLeftCandidateKey
      ? candidateByKey[effectiveLeftCandidateKey]
      : null) ?? null;
  const rightCandidate =
    (effectiveRightCandidateKey
      ? candidateByKey[effectiveRightCandidateKey]
      : null) ?? null;
  const activeCandidate =
    activeCompareSlot === "left" ? leftCandidate : rightCandidate;

  async function onSaveUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const buffer = await file.arrayBuffer();
      const parsed = parsePokemonUnboundSave(buffer);
      setSaveData(parsed);
      setSaveFileName(file.name);
      setSaveError("");
    } catch (error) {
      setSaveData(null);
      setSaveFileName(file.name);
      setSaveError(
        error instanceof Error
          ? error.message
          : "Failed to parse the save file.",
      );
    }
  }

  function assignCandidate(slot: CompareSlotId, candidateKey: string) {
    if (slot === "left") {
      setLeftCandidateKey(candidateKey);
      setActiveCompareSlot("left");
      return;
    }

    setRightCandidateKey(candidateKey);
    setActiveCompareSlot("right");
  }

  return (
    <main className="mx-auto w-[min(1440px,calc(100vw-32px))] px-0 pb-12 pt-8 max-md:w-[min(100vw-20px,1440px)] max-md:pt-5">
      <section className="rounded-[28px] border border-white/10 bg-[linear-gradient(135deg,rgba(16,39,52,0.95),rgba(31,122,92,0.88))] p-8 text-slate-50 shadow-[0_24px_60px_rgba(38,43,53,0.12)] max-md:rounded-[20px] max-md:p-5">
        <p className="mb-2 text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--accent)]">
          Pokemon Unbound Save Reader
        </p>
        <h1 className="max-w-[12ch] text-[clamp(2.4rem,4vw,4.8rem)] leading-[0.94] tracking-[-0.06em] max-md:max-w-none">
          Read your save, load a gym, and scout your best answers.
        </h1>
        <p className="mt-[18px] max-w-[72ch] text-base leading-6 text-slate-50/80">
          Upload a Pokemon Unbound `.sav`, choose the gym leader and difficulty,
          then compare two candidates from your party and boxes against the full
          enemy team using the extracted source dataset.
        </p>
      </section>

      {loadError ? (
        <p className="mt-3 font-semibold text-[var(--danger)]">{loadError}</p>
      ) : null}

      <section className="flex flex-col ">
        <article className=" border border-[rgba(29,35,48,0.12)] bg-[rgba(255,252,245,0.84)]  shadow-[0_24px_60px_rgba(38,43,53,0.12)] backdrop-blur-[14px] max-md:rounded-[20px] max-md:p-5">
          <div className=" flex items-start justify-between gap-4">
            <div className="flex flex-row ">
              <p className="text-[16px] font-bold tracking-[-0.04em]">
                Gym leader team
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <select
                className="min-h-6 min-w-[180px] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
                value={effectiveSelectedGymLeader}
                onChange={(event) => setSelectedGymLeader(event.target.value)}
              >
                {availableGyms.map((gym) => (
                  <option key={gym.leader} value={gym.leader}>
                    {gym.gymNumber}. {gym.leader} ({gym.location})
                  </option>
                ))}
              </select>
              <select
                className="min-h-6 min-w-[180px] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
                value={effectiveSelectedDifficulty}
                onChange={(event) => setSelectedDifficulty(event.target.value)}
              >
                {availableDifficulties.map((difficulty) => (
                  <option
                    key={`${effectiveSelectedGymLeader}:${difficulty.difficulty}`}
                    value={difficulty.difficulty}
                  >
                    {difficulty.difficulty}
                  </option>
                ))}
              </select>
              <input
                className="min-h-6 min-w-[180px] max-w-[140px] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
                inputMode="numeric"
                value={manualLevelCap}
                onChange={(event) =>
                  setManualLevelCap(event.target.value.replace(/[^\d]/g, ""))
                }
                placeholder={String(defaultLevelCap)}
              />
            </div>
          </div>

          {selectedGym ? (
            <>
              <div className="mt-0 flex justify-center">
                {gymTeam.map((pokemon) => (
                  <button
                    className={`flex flex-col cursor-pointer  border-[3px] border-[#3e6978] bg-[#b88e6f] text-left  ${
                      selectedEnemy?.id === pokemon.id
                        ? "outline outline-3 outline-offset-3 z-1 outline-[#ff0000]"
                        : ""
                    }`}
                    key={pokemon.id}
                    onClick={() => setSelectedEnemyId(pokemon.id)}
                    type="button"
                  >
                    <div className="flex justify-center">
                      <div className="flex items-center justify-center rounded-[14px] bg-white/95 p-2">
                        {getSpriteUrl(pokemon) ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            alt={pokemon.name}
                            className="h-[70] w-[70] object-contain"
                            src={getSpriteUrl(pokemon) ?? undefined}
                          />
                        ) : (
                          <div className="flex h-16 w-16 items-center justify-center border border-[rgba(31,122,92,0.16)] bg-[linear-gradient(135deg,rgba(31,122,92,0.16),rgba(226,170,61,0.3))] text-[1.15rem] font-extrabold text-[var(--accent-strong)]">
                            {getPortraitLabel(pokemon.name)}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col  bg-white/30">
                        <div className="text-center">
                          <div className="flex flex-wrap justify-center ">
                            {pokemon.types.map((type) => (
                              <span
                                className="min-w-16 rounded px-2 py-1 text-center text-[0.8rem] font-bold text-white"
                                key={`${pokemon.id}:${type}`}
                                style={{ background: getTypeColor(type) }}
                              >
                                {type}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="relative group">
                          {/* Trigger */}
                          <div className="rounded-xl bg-white/80 p-1 text-[0.8rem] text-center text-[#111827]">
                            {pokemon.ability ?? "Unknown ability"}
                          </div>

                          {/* Tooltip shown on hover */}
                          <div className="absolute hidden group-hover:block top-full left-0 mt-1 px-2 py-1 bg-white border border-gray-200 rounded shadow text-sm whitespace-nowrap z-10">
                            Ability
                          </div>
                        </div>
                        <div className="rounded-xl bg-white/80 p-1 text-center text-[#111827]">
                          <div className="relative group">
                            {/* Trigger */}
                            <div className="text-[0.8rem]">
                              {pokemon.heldItem ?? "None"}
                            </div>

                            {/* Tooltip shown on hover */}
                            <div className="absolute hidden group-hover:block top-full left-0 mt-1 px-2 py-1 bg-white border border-gray-200 rounded shadow text-sm whitespace-nowrap z-10">
                              item
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl bg-white/95 px-1 py-1 text-center text-[0.8rem] font-bold text-[#111827]">
                      {`${pokemon.name} `}

                      <small>Lv.</small>
                      {pokemon.level}
                      {` ${getNatureSummary(pokemon.nature)}`}
                    </div>
                    <div className="rounded-xl bg-white/95 px-1 py-1  text-[0.8rem] text-center text-[#111827]">
                      {pokemon.evSpread ?? "No EV spread listed"}
                    </div>

                    <div className="flex flex-col">
                      {pokemon.moveSummaries.map((move) => {
                        const multiplier = activeCandidate
                          ? getTypeEffectiveness(
                              move.type,
                              activeCandidate.types,
                            )
                          : 1;

                        return (
                          <div
                            className="flex rounded-xl border-2 bg-white/95 px-1"
                            key={`${pokemon.id}:${move.name}`}
                            style={{
                              background: getMoveEffectivenessColor(multiplier),
                            }}
                          >
                            <div className="flex justify-between w-full items-center text-center font-bold text-[0.8rem] text-[#111827]">
                              {move.name}
                            </div>
                            <div className="flex">
                              <div className="flex gap-0">
                                <span
                                  className="rounded w-full px-1.5 py-1 text-center text-[0.72rem] font-bold text-white"
                                  style={{
                                    background: getTypeColor(move.type),
                                  }}
                                >
                                  {move.type}
                                </span>
                                <span
                                  className="rounded px-1.5 py-1 text-center text-[0.72rem] font-bold capitalize text-white"
                                  style={{
                                    background: getCategoryColor(move.category),
                                  }}
                                >
                                  {move.category === "physical"
                                    ? "phy"
                                    : move.category === "special"
                                      ? "spe"
                                      : "sta"}
                                </span>
                              </div>
                              <div className="text-center text-[0.78rem] w-[25px] font-bold text-black]">
                                {formatMultiplier(multiplier)}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="leading-6 text-[var(--muted)]">
              Loading gym leader data...
            </p>
          )}
        </article>

        <article className=" border border-[rgba(29,35,48,0.12)] bg-[rgba(255,252,245,0.84)] p-6 shadow-[0_24px_60px_rgba(38,43,53,0.12)] backdrop-blur-[14px] max-md:rounded-[20px] max-md:p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--accent)]">
                Middle View
              </p>
              <h2 className="text-[1.45rem] font-bold tracking-[-0.04em]">
                Compare two answers
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label
                className="mb-2 block text-[0.86rem] font-semibold text-[var(--muted)]"
                htmlFor="damage-filter"
              >
                Learnset filter
              </label>
              <select
                id="damage-filter"
                className="min-h-11 min-w-[180px] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
                value={damageFilter}
                onChange={(event) =>
                  setDamageFilter(event.target.value as DamageFilter)
                }
              >
                {DAMAGE_FILTERS.map((filter) => (
                  <option key={filter.value} value={filter.value}>
                    {filter.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-[18px] max-md:grid-cols-1">
            {(
              [
                ["left", leftCandidate],
                ["right", rightCandidate],
              ] as const
            ).map(([slot, candidate]) => (
              <article
                className={`grid gap-[14px] rounded-[22px] border border-[rgba(29,35,48,0.12)] bg-white/70 p-5 ${
                  activeCompareSlot === slot
                    ? "border-[rgba(31,122,92,0.45)] bg-[rgba(31,122,92,0.1)] shadow-[inset_0_0_0_1px_rgba(31,122,92,0.2)]"
                    : ""
                }`}
                key={slot}
                onClick={() => setActiveCompareSlot(slot)}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[0.75rem] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                    {slot === "left" ? "Slot 1" : "Slot 2"}
                  </span>
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[rgba(31,122,92,0.16)] bg-[linear-gradient(135deg,rgba(31,122,92,0.16),rgba(226,170,61,0.3))] text-[1.15rem] font-extrabold text-[var(--accent-strong)]">
                    {candidate ? getPortraitLabel(candidate.speciesName) : "?"}
                  </div>
                </div>
                {candidate ? (
                  <>
                    <h3>{candidate.displayName}</h3>
                    <p className="leading-6 text-[var(--muted)]">
                      {candidate.locationLabel} • {candidate.types.join(" / ")}{" "}
                      • Lv.{candidate.level}
                    </p>
                    {candidate.methodLabel ? (
                      <p className="mt-4 leading-[1.55] text-[var(--foreground)]">
                        {candidate.methodLabel}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap gap-x-3 gap-y-2 text-[0.84rem] leading-[1.4] text-[var(--muted)]">
                      <span>Nature: {candidate.nature}</span>
                      <span>Held item: {candidate.heldItemName ?? "None"}</span>
                    </div>
                    <div className="grid gap-3">
                      <StatBlock stats={candidate.stats} />
                      <div className="rounded-[18px] border border-[rgba(29,35,48,0.12)] bg-[rgba(255,248,231,0.96)] px-4 py-3">
                        <span className="text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--muted)]">
                          BST
                        </span>
                        <strong className="mt-1 block text-lg leading-[1.2] text-[var(--foreground)]">
                          {inferStatlineTotal(candidate.stats)}
                        </strong>
                      </div>
                    </div>
                    <p className="mt-4 leading-[1.55] text-[var(--foreground)]">
                      Current moves: {candidate.currentMoveSummary}
                    </p>
                    <div className="grid max-h-[460px] gap-2.5 overflow-auto pr-1">
                      {candidate.learnset
                        .filter((move) =>
                          selectedEnemy
                            ? moveMatchesFilter(
                                move,
                                selectedEnemy.types,
                                damageFilter,
                              )
                            : true,
                        )
                        .map((move) => {
                          const multiplier = selectedEnemy
                            ? getTypeEffectiveness(
                                move.type,
                                selectedEnemy.types,
                              )
                            : 1;

                          return (
                            <div
                              className="grid gap-1 rounded-2xl border border-[rgba(29,35,48,0.12)] bg-white/70 px-[14px] py-3"
                              key={`${candidate.key}:${move.name}:${move.source}:${move.detailLabel}`}
                            >
                              <strong>
                                {move.name}{" "}
                                {selectedEnemy
                                  ? formatMultiplier(multiplier)
                                  : ""}
                              </strong>
                              <span className="text-[var(--muted)]">
                                {move.detailLabel} • {move.type} •{" "}
                                {move.category} • Power {move.power}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  </>
                ) : (
                  <p className="leading-6 text-[var(--muted)]">
                    Assign a Pokemon from the save list below.
                  </p>
                )}
              </article>
            ))}

            <article className="flex flex-col  border border-[rgba(29,35,48,0.12)] bg-[radial-gradient(circle_at_top_right,rgba(226,170,61,0.18),transparent_34%),rgba(255,255,255,0.74)] p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[0.75rem] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                  Enemy focus
                </span>
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[rgba(31,122,92,0.16)] bg-[linear-gradient(135deg,rgba(31,122,92,0.16),rgba(226,170,61,0.3))] text-[1.15rem] font-extrabold text-[var(--accent-strong)]">
                  {selectedEnemy && getSpriteUrl(selectedEnemy) ? (
                    <img
                      alt={selectedEnemy.name}
                      className="h-[70px] w-[70px] object-contain"
                      src={getSpriteUrl(selectedEnemy) ?? undefined}
                    />
                  ) : (
                    <span>
                      {selectedEnemy
                        ? getPortraitLabel(selectedEnemy.name)
                        : "?"}
                    </span>
                  )}
                </div>
              </div>
              {selectedEnemy ? (
                <>
                  <h3>
                    {selectedEnemy.name} Lv.{selectedEnemy.level}
                  </h3>
                  <p className="leading-6 text-[var(--muted)]">
                    {selectedEnemy.types.join(" / ")}
                  </p>
                  <div className="flex flex-wrap gap-x-3 gap-y-2 text-[0.84rem] leading-[1.4] text-[var(--muted)]">
                    <span>Ability: {selectedEnemy.ability ?? "Unknown"}</span>
                    <span>Held item: {selectedEnemy.heldItem ?? "None"}</span>
                    <span>Nature: {selectedEnemy.nature ?? "Unknown"}</span>
                  </div>
                  <div className="grid gap-3">
                    <StatBlock stats={selectedEnemy.baseStats} />
                    <div className="rounded-[18px] border border-[rgba(29,35,48,0.12)] bg-[rgba(255,248,231,0.96)] px-4 py-3">
                      <span className="text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--muted)]">
                        BST
                      </span>
                      <strong className="mt-1 block text-lg leading-[1.2] text-[var(--foreground)]">
                        {inferStatlineTotal(selectedEnemy.baseStats)}
                      </strong>
                    </div>
                  </div>
                  <div className="grid max-h-[460px] gap-2.5 overflow-auto pr-1">
                    {selectedEnemy.moveSummaries.map((move) => {
                      const multiplier = activeCandidate
                        ? getTypeEffectiveness(move.type, activeCandidate.types)
                        : 1;
                      const damage =
                        activeCandidate && move.category !== "status"
                          ? calculateMoveDamage({
                              attackerLevel: selectedEnemy.level,
                              attackerStats: selectedEnemy.baseStats,
                              attackerTypes: selectedEnemy.types,
                              attackType: move.category,
                              defenderStats: activeCandidate.stats,
                              defenderTypes: activeCandidate.types,
                              movePower: move.power,
                              moveType: move.type,
                            })
                          : null;

                      return (
                        <div
                          className="grid gap-1 rounded-2xl border border-[rgba(29,35,48,0.12)] bg-white/70 px-[14px] py-3"
                          key={`${selectedEnemy.id}:${move.name}`}
                        >
                          <strong>
                            {move.name} {formatMultiplier(multiplier)}
                          </strong>
                          <span className="text-[var(--muted)]">
                            {move.type} • {move.category} • Power {move.power}
                            {damage !== null ? ` • ~${damage} damage` : ""}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="leading-6 text-[var(--muted)]">
                  Choose a gym leader Pokemon to inspect its stats and moves.
                </p>
              )}
            </article>
          </div>
        </article>

        <article className="rounded-[24px] border border-[rgba(29,35,48,0.12)] bg-[rgba(255,252,245,0.84)] p-6 shadow-[0_24px_60px_rgba(38,43,53,0.12)] backdrop-blur-[14px] max-md:rounded-[20px] max-md:p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--accent)]">
                Bottom View
              </p>
              <h2 className="text-[1.45rem] font-bold tracking-[-0.04em]">
                Upload your save and search every Pokemon
              </h2>
            </div>
            <label className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-full border border-transparent bg-[var(--accent)] px-[18px] font-bold text-white">
              Load `.sav`
              <input type="file" accept=".sav,.srm" onChange={onSaveUpload} />
            </label>
          </div>

          {saveFileName ? (
            <p className="mt-4 leading-[1.55] text-[var(--foreground)]">
              Loaded `{saveFileName}`
              {saveData ? ` (${prettyFileSize(saveData.fileSize)})` : ""}.
            </p>
          ) : (
            <p className="leading-6 text-[var(--muted)]">
              Upload a Pokemon Unbound save to search your party and boxes and
              assign candidates into the two comparison slots.
            </p>
          )}

          {saveData ? (
            <>
              <div className="mt-4 flex flex-wrap gap-2.5">
                <span className="rounded-full bg-[rgba(31,122,92,0.12)] px-3 py-2 text-[0.86rem] font-semibold text-[var(--accent-strong)]">
                  {saveData.party.length} party Pokemon
                </span>
                <span className="rounded-full bg-[rgba(31,122,92,0.12)] px-3 py-2 text-[0.86rem] font-semibold text-[var(--accent-strong)]">
                  {saveData.pokemon.length - saveData.party.length} boxed
                  Pokemon found
                </span>
                <span className="rounded-full bg-[rgba(31,122,92,0.12)] px-3 py-2 text-[0.86rem] font-semibold text-[var(--accent-strong)]">
                  Current box {saveData.currentBox + 1}
                </span>
              </div>
              {saveData.warnings.length > 0 ? (
                <div className="mt-[14px] rounded-2xl border border-[rgba(226,170,61,0.24)] bg-[rgba(226,170,61,0.1)] px-4 py-[14px]">
                  {saveData.warnings.map((warning) => (
                    <p className="leading-6 text-[var(--muted)]" key={warning}>
                      {warning}
                    </p>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}

          {saveError ? (
            <p className="mt-3 font-semibold text-[var(--danger)]">
              {saveError}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <input
              className="min-h-11 min-w-[180px] min-w-[min(320px,100%)] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
              placeholder="Search by species or type"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="min-h-11 min-w-[180px] rounded-[14px] border border-[rgba(29,35,48,0.12)] bg-white/90 px-3.5 text-[var(--foreground)]"
              value={typeFilter}
              onChange={(event) =>
                setTypeFilter(event.target.value as PokemonType | "All")
              }
            >
              {TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>
                  {type === "All" ? "All types" : type}
                </option>
              ))}
            </select>
            <label className="inline-flex items-center gap-2 text-[var(--foreground)]">
              <input
                checked={showEvolutions}
                onChange={(event) => setShowEvolutions(event.target.checked)}
                type="checkbox"
              />
              Show evolutions under cap
            </label>
          </div>

          <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3 max-md:grid-cols-1">
            {filteredCandidates.map((candidate) => {
              const isLeft = leftCandidate?.key === candidate.key;
              const isRight = rightCandidate?.key === candidate.key;

              return (
                <div
                  className="grid gap-3 rounded-[18px] border border-[rgba(29,35,48,0.12)] bg-white/70 p-4 text-left"
                  key={candidate.key}
                >
                  <div className="flex items-center gap-[14px]">
                    <div className="flex h-[52px] w-[52px] items-center justify-center rounded-2xl border border-[rgba(31,122,92,0.16)] bg-[linear-gradient(135deg,rgba(31,122,92,0.16),rgba(226,170,61,0.3))] text-base font-extrabold text-[var(--accent-strong)]">
                      {getPortraitLabel(candidate.speciesName)}
                    </div>
                    <div>
                      <strong>{candidate.displayName}</strong>
                      <span className="block text-[var(--muted)]">
                        {candidate.locationLabel} • Lv.{candidate.level}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-2 text-[0.84rem] leading-[1.4] text-[var(--muted)]">
                    <span>{candidate.types.join(" / ")}</span>
                    <span>Held item: {candidate.heldItemName ?? "None"}</span>
                    <span>Nature: {candidate.nature}</span>
                  </div>
                  {candidate.methodLabel ? (
                    <p className="leading-6 text-[var(--muted)]">
                      {candidate.methodLabel}
                    </p>
                  ) : null}
                  <p className="leading-6 text-[var(--muted)]">
                    Current moves: {candidate.currentMoveSummary}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-2.5">
                    <button
                      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-full border px-[18px] font-bold ${
                        isLeft
                          ? "border-transparent bg-[var(--accent)] text-white"
                          : "border-[rgba(31,122,92,0.18)] bg-[rgba(31,122,92,0.12)] text-[var(--accent-strong)]"
                      }`}
                      onClick={() => assignCandidate("left", candidate.key)}
                      type="button"
                    >
                      {isLeft ? "Assigned to slot 1" : "Use in slot 1"}
                    </button>
                    <button
                      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-full border px-[18px] font-bold ${
                        isRight
                          ? "border-transparent bg-[var(--accent)] text-white"
                          : "border-[rgba(31,122,92,0.18)] bg-[rgba(31,122,92,0.12)] text-[var(--accent-strong)]"
                      }`}
                      onClick={() => assignCandidate("right", candidate.key)}
                      type="button"
                    >
                      {isRight ? "Assigned to slot 2" : "Use in slot 2"}
                    </button>
                  </div>
                </div>
              );
            })}
            {saveData && filteredCandidates.length === 0 ? (
              <p className="leading-6 text-[var(--muted)]">
                No Pokemon match the current search and type filters.
              </p>
            ) : null}
          </div>
        </article>
      </section>
    </main>
  );
}
