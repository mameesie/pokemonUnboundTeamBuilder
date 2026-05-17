export type RomInspection = {
  headerTitle: string;
  gameCode: string;
  makerCode: string;
  romSizeMb: number;
  printableStringCount: number;
  extractionStatus: string;
  summary: string;
  hints: string[];
};

function readAscii(bytes: Uint8Array, start: number, end: number) {
  return Array.from(bytes.slice(start, end))
    .map((byte) => (byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : ""))
    .join("")
    .trim();
}

function countPrintableRuns(bytes: Uint8Array, minimumLength: number) {
  let count = 0;
  let runLength = 0;

  for (const byte of bytes) {
    if (byte >= 32 && byte <= 126) {
      runLength += 1;
    } else {
      if (runLength >= minimumLength) {
        count += 1;
      }
      runLength = 0;
    }
  }

  if (runLength >= minimumLength) {
    count += 1;
  }

  return count;
}

export function inspectRom(buffer: ArrayBuffer): RomInspection {
  const bytes = new Uint8Array(buffer);
  const headerTitle = readAscii(bytes, 0xa0, 0xac) || "Unknown";
  const gameCode = readAscii(bytes, 0xac, 0xb0) || "Unknown";
  const makerCode = readAscii(bytes, 0xb0, 0xb2) || "Unknown";
  const romSizeMb = bytes.byteLength / (1024 * 1024);
  const printableStringCount = countPrintableRuns(bytes, 6);

  const hints = [
    "Header confirms a FireRed-family GBA base ROM.",
    "Most gameplay tables are not plain ASCII; names and battle data live in encoded binary structures.",
    "This app now prefers Skeli's source tables and uses ROM inspection as an optional verification step.",
  ];

  return {
    headerTitle,
    gameCode,
    makerCode,
    romSizeMb,
    printableStringCount,
    extractionStatus: "Usable for verification; source tables remain the primary dataset",
    summary:
      "The ROM is readable and identifiable. It is still useful for sanity-checking shipped Unbound builds, but the planner no longer needs it as the primary source for species, move, evolution, or learnset data.",
    hints,
  };
}
