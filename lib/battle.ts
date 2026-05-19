export type PokemonType =
  | "Normal"
  | "Fire"
  | "Water"
  | "Electric"
  | "Grass"
  | "Ice"
  | "Fighting"
  | "Poison"
  | "Ground"
  | "Flying"
  | "Psychic"
  | "Bug"
  | "Rock"
  | "Ghost"
  | "Dragon"
  | "Dark"
  | "Steel"
  | "Fairy";

export type MoveCategory = "physical" | "special" | "status";

export type Stats = {
  hp: number;
  atk: number;
  def: number;
  spa: number;
  spd: number;
  spe: number;
};

export type Move = {
  name: string;
  type: PokemonType;
  power: number;
  category: MoveCategory;
};

export type LearnableMove = Move & {
  source: "level-up" | "egg" | "tm" | "tutor";
};

export type EvolutionOption = {
  name: string;
  level: number;
  types: PokemonType[];
  baseStats: Stats;
};

export type PlayerPokemon = {
  id: string;
  name: string;
  nickname?: string;
  level: number;
  types: PokemonType[];
  baseStats: Stats;
  learnset: LearnableMove[];
  evolutions: EvolutionOption[];
};

export type EnemyPokemon = {
  id: string;
  name: string;
  level: number;
  types: PokemonType[];
  baseStats: Stats;
  moves: Move[];
};

export type GymLeader = {
  name: string;
  difficulty: string;
  levelCap: number;
  team: EnemyPokemon[];
};

export type DamageFilter = "super" | "neutral" | "resisted";

export const DAMAGE_FILTERS = [
  { value: "super", label: "Show 2x and 4x moves" },
  { value: "neutral", label: "Show 1x moves" },
  { value: "resisted", label: "Show 0.5x and 0.25x moves" },
] satisfies { value: DamageFilter; label: string }[];

const TYPE_CHART: Record<PokemonType, Partial<Record<PokemonType, number>>> = {
  Normal: { Rock: 0.5, Ghost: 0, Steel: 0.5 },
  Fire: { Fire: 0.5, Water: 0.5, Grass: 2, Ice: 2, Bug: 2, Rock: 0.5, Dragon: 0.5, Steel: 2 },
  Water: { Fire: 2, Water: 0.5, Grass: 0.5, Ground: 2, Rock: 2, Dragon: 0.5 },
  Electric: { Water: 2, Electric: 0.5, Grass: 0.5, Ground: 0, Flying: 2, Dragon: 0.5 },
  Grass: {
    Fire: 0.5,
    Water: 2,
    Grass: 0.5,
    Poison: 0.5,
    Ground: 2,
    Flying: 0.5,
    Bug: 0.5,
    Rock: 2,
    Dragon: 0.5,
    Steel: 0.5,
  },
  Ice: { Fire: 0.5, Water: 0.5, Grass: 2, Ground: 2, Flying: 2, Dragon: 2, Steel: 0.5, Ice: 0.5 },
  Fighting: {
    Normal: 2,
    Ice: 2,
    Poison: 0.5,
    Flying: 0.5,
    Psychic: 0.5,
    Bug: 0.5,
    Rock: 2,
    Ghost: 0,
    Dark: 2,
    Steel: 2,
    Fairy: 0.5,
  },
  Poison: { Grass: 2, Poison: 0.5, Ground: 0.5, Rock: 0.5, Ghost: 0.5, Steel: 0, Fairy: 2 },
  Ground: {
    Fire: 2,
    Electric: 2,
    Grass: 0.5,
    Poison: 2,
    Flying: 0,
    Bug: 0.5,
    Rock: 2,
    Steel: 2,
  },
  Flying: { Electric: 0.5, Grass: 2, Fighting: 2, Bug: 2, Rock: 0.5, Steel: 0.5 },
  Psychic: { Fighting: 2, Poison: 2, Psychic: 0.5, Dark: 0, Steel: 0.5 },
  Bug: {
    Fire: 0.5,
    Grass: 2,
    Fighting: 0.5,
    Poison: 0.5,
    Flying: 0.5,
    Psychic: 2,
    Ghost: 0.5,
    Dark: 2,
    Steel: 0.5,
    Fairy: 0.5,
  },
  Rock: { Fire: 2, Ice: 2, Fighting: 0.5, Ground: 0.5, Flying: 2, Bug: 2, Steel: 0.5 },
  Ghost: { Normal: 0, Psychic: 2, Ghost: 2, Dark: 0.5 },
  Dragon: { Dragon: 2, Steel: 0.5, Fairy: 0 },
  Dark: { Fighting: 0.5, Psychic: 2, Ghost: 2, Dark: 0.5, Fairy: 0.5 },
  Steel: { Fire: 0.5, Water: 0.5, Electric: 0.5, Ice: 2, Rock: 2, Steel: 0.5, Fairy: 2 },
  Fairy: { Fire: 0.5, Fighting: 2, Poison: 0.5, Dragon: 2, Dark: 2, Steel: 0.5 },
};

export function getTypeEffectiveness(
  attackingType: PokemonType,
  defendingTypes: PokemonType[],
) {
  if (defendingTypes.length === 0) {
    return 1;
  }

  const typeMatchups = TYPE_CHART[attackingType];
  if (!typeMatchups) {
    return 1;
  }

  return defendingTypes.reduce((multiplier, defendingType) => {
    return multiplier * (typeMatchups[defendingType] ?? 1);
  }, 1);
}

export function getMoveEffectivenessColor(multiplier: number) {
  if (multiplier === 4) {
    return "#ef4444";
  }

  if (multiplier === 2) {
    return "#facc15";
  }

  if (multiplier === 1) {
    return "#d1d5db";
  }

  if (multiplier === 0.5) {
    return "#60a5fa";
  }

  if (multiplier === 0.25) {
    return "#4ade80";
  }

  if (multiplier === 0) {
    return "#4b5563";
  }

  if (multiplier > 2) {
    return "#ef4444";
  }

  if (multiplier > 1) {
    return "#facc15";
  }

  if (multiplier < 0.5) {
    return "#4ade80";
  }

  if (multiplier < 1) {
    return "#60a5fa";
  }

  return "#d1d5db";
}

export function formatMultiplier(multiplier: number) {
  return `${multiplier}x`;
}

type DamageInput = {
  attackerLevel: number;
  attackType: MoveCategory;
  movePower: number;
  moveType: PokemonType;
  attackerTypes: PokemonType[];
  attackerStats: Stats;
  defenderTypes: PokemonType[];
  defenderStats: Stats;
};

export function calculateMoveDamage(input: DamageInput) {
  if (input.attackType === "status" || input.movePower <= 0) {
    return null;
  }

  const attackStat =
    input.attackType === "physical" ? input.attackerStats.atk : input.attackerStats.spa;
  const defenseStat =
    input.attackType === "physical" ? input.defenderStats.def : input.defenderStats.spd;
  const stab = input.attackerTypes.includes(input.moveType) ? 1.5 : 1;
  const effectiveness = getTypeEffectiveness(input.moveType, input.defenderTypes);
  const baseDamage =
    (((2 * input.attackerLevel) / 5 + 2) * input.movePower * (attackStat / defenseStat)) / 50 + 2;

  return Math.max(1, Math.round(baseDamage * stab * effectiveness));
}

export function inferStatlineTotal(stats: Stats) {
  return stats.hp + stats.atk + stats.def + stats.spa + stats.spd + stats.spe;
}
