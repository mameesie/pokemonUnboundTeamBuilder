from __future__ import annotations

from pathlib import Path


CHARMAP: dict[int, str] = {
    0x00: " ",
    0xAB: "!",
    0xAC: "?",
    0xAD: ".",
    0xAE: "-",
    0xB4: "'",
    0xB5: '"',
    0xB8: ",",
    0xBA: "/",
}

for index, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=0xBB):
    CHARMAP[index] = char

for index, char in enumerate("abcdefghijklmnopqrstuvwxyz", start=0xD5):
    CHARMAP[index] = char

for index, char in enumerate("0123456789", start=0xA1):
    CHARMAP[index] = char

CHARMAP.update(
    {
        0x35: "Lv",
        0x36: "=",
        0x51: "PK",
        0x52: "MN",
        0x53: "PO",
        0x54: "KE",
        0x55: "BL",
        0x56: "OC",
        0x57: "K",
        0x58: "I",
        0x59: "CO",
        0x5A: "L",
        0x5B: "M",
        0x5C: "R",
        0x5D: "A",
        0x5E: "T",
        0x5F: "V",
        0x7A: " ",
    }
)


def extract_strings(data: bytes) -> list[tuple[int, str]]:
    strings: list[tuple[int, str]] = []
    current: list[str] = []
    start: int | None = None

    for index, byte in enumerate(data):
        if byte in CHARMAP:
            if start is None:
                start = index
            current.append(CHARMAP[byte])
        elif byte == 0xFF and current:
            decoded = "".join(current)
            if 4 <= len(decoded) <= 24:
                strings.append((start or 0, decoded))
            current = []
            start = None
        else:
            current = []
            start = None

    return strings


def main() -> None:
    rom_path = Path("public/Pokemon Unbound (v2.1.1.1).gba")
    data = rom_path.read_bytes()
    strings = extract_strings(data)
    terms = [
        "Bulba",
        "BULBA",
        "Potion",
        "Tackle",
        "Pikachu",
        "Thunder",
        "Skarmory",
        "Growlithe",
        "Abra",
        "Surf",
    ]
    hits = [(offset, text) for offset, text in strings if any(term in text for term in terms)]
    print("hit count:", len(hits))
    for offset, text in hits[:200]:
        print(hex(offset), text)
    print("total decoded strings:", len(strings))
    print("sample:")
    for offset, text in strings[:40]:
        print(hex(offset), text)


if __name__ == "__main__":
    main()
