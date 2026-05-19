import type { PokemonType } from "@/lib/battle";

const SECTOR_COUNT = 32;
const SECTOR_SIZE = 0x1000;
const SECTOR_DATA_SIZE = 0xff0;
const FOOTER_ID_OFFSET = 0xff4;
const FOOTER_CHECKSUM_OFFSET = 0xff6;
const FOOTER_SIGNATURE_OFFSET = 0xff8;
const FOOTER_COUNTER_OFFSET = 0xffc;
const SAVE_SLOT_SECTOR_COUNT = 14;
const PARTY_SIZE = 6;
const PARTY_MON_SIZE = 0x64;
const PARTY_COUNT_OFFSET = 0x34;
const PARTY_OFFSET = 0x38;
const COMPRESSED_BOX_MON_SIZE = 58;
const MONS_PER_BOX = 30;
const BOX_COUNT_MAIN = 19;
const BOX_COUNT_TOTAL = 25;
const EXTRA_BOXES_CONFIRMED = 3;
const MAIN_BOXES_OFFSET = 0x4;
const EXTRA_DATA_SIZE = 0x2ea4;
const EXTRA_BOXES_OFFSET = 0x19d0;
const SAVE_BLOCK1_BOX23_OFFSET = 0x1f08;
const SAVE_BLOCK1_BOX24_OFFSET = SAVE_BLOCK1_BOX23_OFFSET + MONS_PER_BOX * COMPRESSED_BOX_MON_SIZE;
const SAVE_BLOCK2_BOX25_OFFSET = 0x0b0;
const FILE_SIGNATURE = 0x08012025;

const PARTY_MON_LEVEL_OFFSET = 0x54;
const PARTY_MON_SPECIES_OFFSET = 0x20;
const PARTY_MON_ITEM_OFFSET = 0x22;
const PARTY_MON_MOVES_OFFSET = 0x2c;
const PARTY_MON_NICKNAME_OFFSET = 0x08;
const PARTY_MON_OTID_OFFSET = 0x04;
const PARTY_MON_PERSONALITY_OFFSET = 0x00;
const SAFE_BACKUP_PARTY_OFFSET = 0x458;
const BOX_MON_SIZE = 80;
const BOX_MON_SUBSTRUCT_OFFSET = 0x20;

const COMPRESSED_SPECIES_OFFSET = 0x1c;
const COMPRESSED_ITEM_OFFSET = 0x1e;
const COMPRESSED_NICKNAME_OFFSET = 0x08;
const COMPRESSED_OTID_OFFSET = 0x04;
const COMPRESSED_PERSONALITY_OFFSET = 0x00;
const COMPRESSED_LEVEL_FALLBACK_OFFSET = 0x20;

const PARASITE_CHUNK_OFFSETS = {
  0: 0xcc,
  4: 0x258,
  13: 0xba0,
} as const;

const UPPER_A = 0xbb;
const LOWER_A = 0xd5;
const ZERO = 0xa1;

const NATURES = [
  "Hardy",
  "Lonely",
  "Brave",
  "Adamant",
  "Naughty",
  "Bold",
  "Docile",
  "Relaxed",
  "Impish",
  "Lax",
  "Timid",
  "Hasty",
  "Serious",
  "Jolly",
  "Naive",
  "Modest",
  "Mild",
  "Quiet",
  "Bashful",
  "Rash",
  "Calm",
  "Gentle",
  "Sassy",
  "Careful",
  "Quirky",
] as const;

export type ParsedSavePokemon = {
  boxIndex: number | null;
  slotIndex: number;
  heldItemId: number;
  isParty: boolean;
  level: number;
  moveIds: number[];
  nickname: string | null;
  nature: string;
  personality: number;
  speciesId: number;
  trainerId: number;
};

export type ParsedSaveFile = {
  boxCount: number;
  currentBox: number;
  fileSize: number;
  party: ParsedSavePokemon[];
  pokemon: ParsedSavePokemon[];
  warnings: string[];
};

type SaveSector = {
  checksum: number;
  counter: number;
  data: Uint8Array;
  id: number;
  signature: number;
};

type SaveSlot = {
  counter: number;
  sectors: Map<number, SaveSector>;
};

export function parsePokemonUnboundSave(buffer: ArrayBuffer): ParsedSaveFile {
  const bytes = new Uint8Array(buffer);

  if (bytes.byteLength < SECTOR_COUNT * SECTOR_SIZE) {
    throw new Error("This save file is smaller than a full FireRed/Unbound save image.");
  }

  const sectors = loadSectors(bytes);
  const slots = [buildSlot(sectors, 0), buildSlot(sectors, SAVE_SLOT_SECTOR_COUNT)];
  const activeSlot = pickLatestSlot(slots);

  if (!activeSlot) {
    throw new Error("Could not find a valid save slot in this `.sav` file.");
  }

  const saveBlock2 = concatChunkData(activeSlot.sectors, [0]);
  const saveBlock1 = concatChunkData(activeSlot.sectors, [1, 2, 3, 4]);
  const storageChunk = concatChunkData(activeSlot.sectors, [5, 6, 7, 8, 9, 10, 11, 12, 13]);
  const extraData = buildExpandedSaveData(activeSlot.sectors, sectors);

  const currentBox = storageChunk[0] ?? 0;
  const partyCount = clamp(saveBlock1[PARTY_COUNT_OFFSET] ?? 0, 0, PARTY_SIZE);
  const party = parsePartyPokemon(saveBlock1, partyCount);
  const boxed = parseBoxPokemon(saveBlock1, saveBlock2, storageChunk, extraData);
  const pokemon = [...party, ...boxed];
  const warnings: string[] = [];

  if (extraData.length < EXTRA_DATA_SIZE) {
    warnings.push("Expanded Unbound save data is incomplete; some extra boxes may be missing.");
  }

  return {
    boxCount: BOX_COUNT_TOTAL,
    currentBox,
    fileSize: bytes.byteLength,
    party,
    pokemon,
    warnings,
  };
}

export function readNature(personality: number) {
  return NATURES[personality % NATURES.length];
}

export function readTypeSummary(types: PokemonType[]) {
  return types.length > 0 ? types.join(" / ") : "Unknown";
}

function loadSectors(bytes: Uint8Array) {
  const sectors: SaveSector[] = [];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  for (let sectorIndex = 0; sectorIndex < SECTOR_COUNT; sectorIndex += 1) {
    const start = sectorIndex * SECTOR_SIZE;
    const signature = view.getUint32(start + FOOTER_SIGNATURE_OFFSET, true);
    const id = view.getUint16(start + FOOTER_ID_OFFSET, true);
    const checksum = view.getUint16(start + FOOTER_CHECKSUM_OFFSET, true);
    const counter = view.getUint32(start + FOOTER_COUNTER_OFFSET, true);
    sectors.push({
      checksum,
      counter,
      data: bytes.slice(start, start + SECTOR_DATA_SIZE),
      id,
      signature,
    });
  }

  return sectors;
}

function buildSlot(sectors: SaveSector[], startIndex: number): SaveSlot | null {
  const byId = new Map<number, SaveSector>();
  let latestCounter = -1;

  for (let index = 0; index < SAVE_SLOT_SECTOR_COUNT; index += 1) {
    const sector = sectors[startIndex + index];
    if (!sector) {
      continue;
    }

    if (sector.id < 0 || sector.id >= SAVE_SLOT_SECTOR_COUNT) {
      continue;
    }

    if (!isLikelySectorSignature(sector.signature)) {
      continue;
    }

    const expectedChecksum = calculateSaveChecksum(sector.data, expectedChunkSize(sector.id));
    if (expectedChecksum !== sector.checksum) {
      continue;
    }

    byId.set(sector.id, sector);
    latestCounter = Math.max(latestCounter, sector.counter);
  }

  if (byId.size !== SAVE_SLOT_SECTOR_COUNT) {
    return null;
  }

  return {
    counter: latestCounter,
    sectors: byId,
  };
}

function pickLatestSlot(slots: Array<SaveSlot | null>) {
  const validSlots = slots.filter((slot): slot is SaveSlot => slot !== null);

  if (validSlots.length === 0) {
    return null;
  }

  return validSlots.reduce((best, candidate) =>
    compareCounters(candidate.counter, best.counter) > 0 ? candidate : best,
  );
}

function compareCounters(left: number, right: number) {
  const leftSigned = left | 0;
  const rightSigned = right | 0;

  if ((leftSigned === -1 && rightSigned === 0) || (leftSigned === 0 && rightSigned === -1)) {
    return leftSigned === 0 ? 1 : -1;
  }

  if (leftSigned === rightSigned) {
    return 0;
  }

  return leftSigned > rightSigned ? 1 : -1;
}

function concatChunkData(sectors: Map<number, SaveSector>, chunkIds: number[]) {
  const totalSize = chunkIds.reduce((size, chunkId) => size + expectedChunkSize(chunkId), 0);
  const output = new Uint8Array(totalSize);
  let offset = 0;

  for (const chunkId of chunkIds) {
    const sector = sectors.get(chunkId);
    if (!sector) {
      throw new Error(`Missing save chunk ${chunkId}.`);
    }

    const size = expectedChunkSize(chunkId);
    output.set(sector.data.slice(0, size), offset);
    offset += size;
  }

  return output;
}

function buildExpandedSaveData(activeSectors: Map<number, SaveSector>, allSectors: SaveSector[]) {
  const output = new Uint8Array(EXTRA_DATA_SIZE);
  let offset = 0;

  for (const chunkId of [0, 4, 13] as const) {
    const sector = activeSectors.get(chunkId);
    if (!sector) {
      continue;
    }

    const parasiteSize = PARASITE_CHUNK_OFFSETS[chunkId];
    const start = SECTOR_DATA_SIZE - parasiteSize;
    output.set(sector.data.slice(start, start + parasiteSize), offset);
    offset += parasiteSize;
  }

  for (const extraSectorIndex of [30, 31]) {
    const sector = allSectors[extraSectorIndex];
    if (!sector) {
      continue;
    }

    output.set(sector.data.slice(0, SECTOR_DATA_SIZE), offset);
    offset += SECTOR_DATA_SIZE;
  }

  return output;
}

function parsePartyPokemon(saveBlock1: Uint8Array, partyCount: number) {
  const party: ParsedSavePokemon[] = [];

  for (let slotIndex = 0; slotIndex < PARTY_SIZE; slotIndex += 1) {
    const offset = PARTY_OFFSET + slotIndex * PARTY_MON_SIZE;
    const mon = saveBlock1.slice(offset, offset + PARTY_MON_SIZE);
    const backupOffset = SAFE_BACKUP_PARTY_OFFSET + slotIndex * BOX_MON_SIZE;
    const backupMon = saveBlock1.slice(backupOffset, backupOffset + BOX_MON_SIZE);
    const fallback = decodeBoxMon(backupMon);
    const liveSpeciesId = readU16(mon, PARTY_MON_SPECIES_OFFSET);
    const liveMoveIds = readPartyMoveIds(mon);
    const speciesId = liveSpeciesId || fallback.speciesId;

    if (speciesId === 0 || slotIndex >= partyCount) {
      continue;
    }

    party.push({
      boxIndex: null,
      heldItemId: readU16(mon, PARTY_MON_ITEM_OFFSET) || fallback.heldItemId,
      isParty: true,
      level: mon[PARTY_MON_LEVEL_OFFSET] ?? 1,
      moveIds: liveMoveIds.length > 0 ? liveMoveIds : fallback.moveIds,
      nickname: decodePokemonText(mon.slice(PARTY_MON_NICKNAME_OFFSET, PARTY_MON_NICKNAME_OFFSET + 10)),
      nature: readNature(readU32(mon, PARTY_MON_PERSONALITY_OFFSET)),
      personality: readU32(mon, PARTY_MON_PERSONALITY_OFFSET),
      slotIndex,
      speciesId,
      trainerId: readU32(mon, PARTY_MON_OTID_OFFSET),
    });
  }

  return party;
}

function parseBoxPokemon(
  saveBlock1: Uint8Array,
  saveBlock2: Uint8Array,
  storageChunk: Uint8Array,
  extraData: Uint8Array,
) {
  const boxed: ParsedSavePokemon[] = [];

  for (let boxIndex = 0; boxIndex < BOX_COUNT_MAIN; boxIndex += 1) {
    const baseOffset = MAIN_BOXES_OFFSET + boxIndex * MONS_PER_BOX * COMPRESSED_BOX_MON_SIZE;
    boxed.push(...parseCompressedBox(baseOffset, storageChunk, boxIndex));
  }

  for (let extraBoxIndex = 0; extraBoxIndex < EXTRA_BOXES_CONFIRMED; extraBoxIndex += 1) {
    const baseOffset =
      EXTRA_BOXES_OFFSET + extraBoxIndex * MONS_PER_BOX * COMPRESSED_BOX_MON_SIZE;
    boxed.push(...parseCompressedBox(baseOffset, extraData, BOX_COUNT_MAIN + extraBoxIndex));
  }

  boxed.push(...parseCompressedBox(SAVE_BLOCK1_BOX23_OFFSET, saveBlock1, 22));
  boxed.push(...parseCompressedBox(SAVE_BLOCK1_BOX24_OFFSET, saveBlock1, 23));
  boxed.push(...parseCompressedBox(SAVE_BLOCK2_BOX25_OFFSET, saveBlock2, 24));

  return boxed;
}

function parseCompressedBox(baseOffset: number, bytes: Uint8Array, boxIndex: number) {
  const boxed: ParsedSavePokemon[] = [];

  for (let slotIndex = 0; slotIndex < MONS_PER_BOX; slotIndex += 1) {
    const offset = baseOffset + slotIndex * COMPRESSED_BOX_MON_SIZE;
    const mon = bytes.slice(offset, offset + COMPRESSED_BOX_MON_SIZE);
    const speciesId = readU16(mon, COMPRESSED_SPECIES_OFFSET);

    if (speciesId === 0) {
      continue;
    }

    const personality = readU32(mon, COMPRESSED_PERSONALITY_OFFSET);
    boxed.push({
      boxIndex,
      heldItemId: readU16(mon, COMPRESSED_ITEM_OFFSET),
      isParty: false,
      level: inferBoxMonLevel(mon),
      moveIds: readCompressedMoveIds(mon),
      nickname: decodePokemonText(mon.slice(COMPRESSED_NICKNAME_OFFSET, COMPRESSED_NICKNAME_OFFSET + 10)),
      nature: readNature(personality),
      personality,
      slotIndex,
      speciesId,
      trainerId: readU32(mon, COMPRESSED_OTID_OFFSET),
    });
  }

  return boxed;
}

function inferBoxMonLevel(mon: Uint8Array) {
  return mon[COMPRESSED_LEVEL_FALLBACK_OFFSET] || 1;
}

function readPartyMoveIds(mon: Uint8Array) {
  const moves: number[] = [];

  for (let index = 0; index < 4; index += 1) {
    const moveId = readU16(mon, PARTY_MON_MOVES_OFFSET + index * 2);
    if (moveId > 0) {
      moves.push(moveId);
    }
  }

  return moves;
}

function decodeBoxMon(mon: Uint8Array) {
  if (mon.length < BOX_MON_SIZE) {
    return {
      heldItemId: 0,
      moveIds: [] as number[],
      speciesId: 0,
    };
  }

  const personality = readU32(mon, COMPRESSED_PERSONALITY_OFFSET);
  const trainerId = readU32(mon, COMPRESSED_OTID_OFFSET);
  const key = personality ^ trainerId;
  const order = BOX_SUBSTRUCT_ORDERS[personality % BOX_SUBSTRUCT_ORDERS.length];
  const decryptedSubstructs = new Uint8Array(48);

  for (let offset = 0; offset < decryptedSubstructs.length; offset += 4) {
    const value = readU32(mon, BOX_MON_SUBSTRUCT_OFFSET + offset) ^ key;
    writeU32(decryptedSubstructs, offset, value);
  }

  const growthOffset = order.indexOf(0) * 12;
  const attacksOffset = order.indexOf(1) * 12;
  const speciesId = readU16(decryptedSubstructs, growthOffset);
  const heldItemId = readU16(decryptedSubstructs, growthOffset + 2);
  const moveIds: number[] = [];

  for (let index = 0; index < 4; index += 1) {
    const moveId = readU16(decryptedSubstructs, attacksOffset + index * 2);
    if (moveId > 0) {
      moveIds.push(moveId);
    }
  }

  return {
    heldItemId,
    moveIds,
    speciesId,
  };
}

function readCompressedMoveIds(mon: Uint8Array) {
  const packedMoves =
    (mon[0x27] ?? 0) +
    (mon[0x28] ?? 0) * 0x100 +
    (mon[0x29] ?? 0) * 0x10000 +
    (mon[0x2a] ?? 0) * 0x1000000 +
    (mon[0x2b] ?? 0) * 0x100000000;

  const moveIds = [
    packedMoves & 0x3ff,
    (packedMoves >> 10) & 0x3ff,
    (packedMoves >> 20) & 0x3ff,
    (packedMoves >> 30) & 0x3ff,
  ];

  return moveIds.filter((moveId) => moveId > 0);
}

function decodePokemonText(bytes: Uint8Array) {
  let output = "";

  for (const value of bytes) {
    if (value === 0xff) {
      break;
    }

    if (value === 0x00) {
      output += " ";
      continue;
    }

    if (value >= ZERO && value <= ZERO + 9) {
      output += String(value - ZERO);
      continue;
    }

    if (value >= UPPER_A && value <= UPPER_A + 25) {
      output += String.fromCharCode("A".charCodeAt(0) + (value - UPPER_A));
      continue;
    }

    if (value >= LOWER_A && value <= LOWER_A + 25) {
      output += String.fromCharCode("a".charCodeAt(0) + (value - LOWER_A));
      continue;
    }

    output += CHAR_MAP[value] ?? "";
  }

  const trimmed = output.replace(/\s+/g, " ").trim();
  return trimmed.length > 0 ? trimmed : null;
}

function calculateSaveChecksum(bytes: Uint8Array, size: number) {
  let sum = 0;

  for (let offset = 0; offset < size; offset += 4) {
    sum += readU32(bytes, offset);
  }

  return ((sum & 0xffff) + (sum >>> 16)) & 0xffff;
}

function expectedChunkSize(chunkId: number) {
  if (chunkId === 0) {
    return 0xf24;
  }

  if (chunkId >= 1 && chunkId <= 3) {
    return 0xff0;
  }

  if (chunkId === 4) {
    return 0xd98;
  }

  if (chunkId >= 5 && chunkId <= 12) {
    return 0xff0;
  }

  if (chunkId === 13) {
    return 0x450;
  }

  throw new Error(`Unsupported save chunk ${chunkId}.`);
}

function isLikelySectorSignature(signature: number) {
  return signature === FILE_SIGNATURE || signature !== 0;
}

function readU16(bytes: Uint8Array, offset: number) {
  return (bytes[offset] ?? 0) | ((bytes[offset + 1] ?? 0) << 8);
}

function readU32(bytes: Uint8Array, offset: number) {
  return (
    (bytes[offset] ?? 0) |
    ((bytes[offset + 1] ?? 0) << 8) |
    ((bytes[offset + 2] ?? 0) << 16) |
    ((bytes[offset + 3] ?? 0) << 24)
  ) >>> 0;
}

function writeU32(bytes: Uint8Array, offset: number, value: number) {
  bytes[offset] = value & 0xff;
  bytes[offset + 1] = (value >>> 8) & 0xff;
  bytes[offset + 2] = (value >>> 16) & 0xff;
  bytes[offset + 3] = (value >>> 24) & 0xff;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

const CHAR_MAP: Record<number, string> = {
  0xab: "!",
  0xac: "?",
  0xad: ".",
  0xae: "-",
  0xb0: "...",
  0xb5: "M",
  0xb6: "F",
  0xb8: ",",
  0xba: "/",
  0xf0: ":",
};

const BOX_SUBSTRUCT_ORDERS = [
  [0, 1, 2, 3],
  [0, 1, 3, 2],
  [0, 2, 1, 3],
  [0, 3, 1, 2],
  [0, 2, 3, 1],
  [0, 3, 2, 1],
  [1, 0, 2, 3],
  [1, 0, 3, 2],
  [2, 0, 1, 3],
  [3, 0, 1, 2],
  [2, 0, 3, 1],
  [3, 0, 2, 1],
  [1, 2, 0, 3],
  [1, 3, 0, 2],
  [2, 1, 0, 3],
  [3, 1, 0, 2],
  [2, 3, 0, 1],
  [3, 2, 0, 1],
  [1, 2, 3, 0],
  [1, 3, 2, 0],
  [2, 1, 3, 0],
  [3, 1, 2, 0],
  [2, 3, 1, 0],
  [3, 2, 1, 0],
] as const;
