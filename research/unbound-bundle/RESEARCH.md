# Pokemon Unbound ROM Research Notes

ROM: `public/Pokemon Unbound (v2.1.1.1).gba`
Header: `BPRE`

## New Source Repositories Added

Two local source drops from Skeli789 were added under `public/`:

- `public/Complete-Fire-Red-Upgrade`
- `public/Dynamic-Pokemon-Expansion`

These are important because they expose the data schema and large plain-text/source tables that we were previously trying to recover from ROM offsets alone.

## What The Source Repos Already Give Us

The following data is available directly from source files rather than only from the bundled `.gba`:

- Species names
  - `public/Dynamic-Pokemon-Expansion/strings/Pokemon_Name_Table.string`
  - exports `gSpeciesNames`

- Base stats
  - `public/Dynamic-Pokemon-Expansion/src/Base_Stats.c`
  - exports `gBaseStats`

- Evolution table
  - `public/Dynamic-Pokemon-Expansion/src/Evolution Table.c`
  - exports `gEvolutionTable`

- Level-up learnsets
  - `public/Dynamic-Pokemon-Expansion/src/Learnsets.c`
  - exports `gLevelUpLearnsets`

- Move names
  - `public/Complete-Fire-Red-Upgrade/strings/attack_name_table.string`
  - exports `gMoveNames`

- Ability names
  - `public/Complete-Fire-Red-Upgrade/strings/ability_name_table.string`
  - exports `gAbilityNames`

- TM compatibility
  - `public/Dynamic-Pokemon-Expansion/src/tm_compatibility/*.txt`

- Tutor compatibility
  - `public/Dynamic-Pokemon-Expansion/src/tutor_compatibility/*.txt`

The dynamic expansion repo also includes a `repointall` file that names the exact runtime symbols it inserts, including:

- `gSpeciesNames`
- `gBaseStats`
- `gEvolutionTable`
- `gLevelUpLearnsets`

## Biggest Implication

Evolution data is no longer "unresolved" at the source-schema level.

We now have an explicit source evolution table in:

- `public/Dynamic-Pokemon-Expansion/src/Evolution Table.c`

That means we do not need to keep hunting blindly for an opaque evolution table layout in the ROM if our goal is to understand the intended engine data model.

## Important Caveat

These repositories look like Skeli789's engine/expansion sources, and they do contain `UNBOUND` conditionals in many engine files. However, this does **not** automatically prove that every value in these checked-in source tables exactly matches the shipped `Pokemon Unbound v2.1.1.1` ROM.

In practice, this means:

- The source repos are strong evidence for table structure and baseline content.
- They are probably good enough to replace ROM parsing for many planner datasets.
- They are not yet a proven byte-for-byte substitute for every Unbound-specific balance tweak or late ROM-only patch.

## Revised Assessment Of The `.gba` Dependency

For the current planner/data-extraction project, the bundled `.gba` probably does **not** need to remain the primary source for:

- species names
- base stats
- evolutions
- level-up learnsets
- move names
- ability names
- TM/tutor compatibility

The `.gba` may still be needed for:

- verifying that the checked-in source tables match shipped Unbound values
- extracting graphics or other compiled assets that are not represented cleanly in source
- discovering truly Unbound-specific data that is not present in the source drops
- validating final runtime offsets when debugging compiled ROM behavior

## Current Project Impact

The current repo still has ROM-first assumptions in these places:

- `scripts/extract_unbound_data.py`
- `scripts/scan_gen3_text.py`
- `app/pokemon-planner-app.tsx`
- `public/extracted/summary.json`

So the research direction should shift from:

- "find every table inside the ROM"

to:

- "prefer source-table extraction from Skeli789 repos"
- "use the ROM only as a verifier or fallback for Unbound-specific deltas"

## Solved

- Species names:
  - ROM offset: `0x166A997`
  - Length: `11` bytes per entry
  - Count: `1293`

- Base stats:
  - ROM offset: `0x19E0CB8`
  - Length: `0x1C` bytes per entry
  - Count: `1293`

- Move names:
  - ROM offset: `0x0A40A10`
  - Length: `13` bytes per entry
  - Count: `923`

- Move battle metadata:
  - ROM offset: `0x0A769AF`
  - Length: `12` bytes per entry
  - Count: `923`
  - Extracted fields:
    - `effectId`
    - `power`
    - `typeId`
    - `accuracy`
    - `pp`
    - `effectChance`
    - `priority`
    - `targetId`
    - `categoryId`

- Ability names:
  - ROM offset: `0x0A36398`
  - Length: `17` bytes per entry
  - Count: `292`

- Partial held-item name block:
  - ROM offset: `0x03DD180`
  - Length: `0x2C` bytes per entry
  - Count: `34`

- Level-up learnset pointer table:
  - ROM offset: `0x1A2457C`
  - Count: `1294`
  - Behavior:
    - reversed pointer array
    - entries decoded as `u16 moveId + u8 level`
    - terminator `moveId=0` and `level=255`

## Strongly Identified But Not Yet Used

- `0x1A212EC`
  - Size is approximately `0x510`
  - This is about one byte per species
  - Probably not evolutions

- `0x1A217FC`
  - `1294` pointers
  - Points to large zero-heavy blocks around `0x189C054`
  - Probably graphics or another non-battle species resource

## Unresolved Candidate Tables

- `0x1A32BDC`
  - `413` pointer/value pairs
  - Continuous index values `0..412`
  - Not the level-up learnset table
  - Pointers land in `0x177xxxx`
  - Contents do not parse cleanly as plain move lists or evolution records
  - Candidate uses:
    - egg moves
    - tutor compatibility
    - other sparse species feature

- `0x1A20B5A`
  - Contains species-ID clusters including:
    - `133, 134, 135, 136, 132, 137, 233, 527`
  - This is not an evolution-record table by itself
  - Looks like a species list used by another system

- `0x1A3F65C`
  - Contains species-ID clusters including:
    - `133, 134, 135, 136, 196, 197, 523, 524, 808`
  - Also appears to be a species list rather than full evolution records

- `0x1A420F4`
  - Plain sequential species IDs
  - Not evolution data

## Evolution Status

Evolution data is now available from source via `public/Dynamic-Pokemon-Expansion/src/Evolution Table.c`.

ROM-level decoding of the compiled evolution table is still unresolved if we specifically need the exact in-ROM layout for `Pokemon Unbound v2.1.1.1`.

## Tried And Ruled Out

- Direct fixed-record evolution scans over the nearby species-data region.
  - Assumption tested:
    - evolution data might be stored as a dense per-species table near the other species resources
    - each species might have a fixed number of slots with small records like `method / param / target`
  - What was tried:
    - broad scans over the `0x19D0000..0x1A25000` range
    - candidate parsers using common Gen 3 style record sizes such as `6` bytes and `8` bytes
    - grouping records into per-species blocks and checking whether Bulbasaur, Ivysaur, Charmander, Wartortle, Eevee, etc. would resolve to plausible targets
  - Result:
    - no candidate region produced consistent starter-line evolutions
    - the hits looked random, repeated, or structurally unrelated to evolutions

- Direct byte-pattern searches for simple `method + level + target species` layouts.
  - Assumption tested:
    - straightforward level evolutions such as Bulbasaur -> Ivysaur and Ivysaur -> Venusaur might expose the record format
  - What was tried:
    - searched for multiple likely little-endian layouts around known target species IDs and expected level values
    - tested layouts equivalent to:
      - `method, 0, level, 0, target, 0`
      - `method, param, target`
      - `method, target, param`
    - repeated the same style of search with other easy cases from early lines
  - Result:
    - no reliable match scaled beyond one-off accidental byte hits
    - nothing gave a format that also worked for the next expected species

- Re-using the obvious species-linked pointer families.
  - `0x1A2457C`
    - tested as a candidate species pointer table for evolutions
    - result:
      - this decoded cleanly as the reversed level-up learnset pointer table
      - entries are `u16 moveId + u8 level`, terminated by `moveId=0`, `level=255`
      - not evolutions
  - `0x1A217FC`
    - tested as another `1294`-entry species pointer table
    - result:
      - pointers land in large zero-heavy blocks around `0x189C054`
      - data shape does not resemble move lists, evolution records, or compact battle metadata
      - likely graphics or another non-battle species resource
  - `0x1A212EC`
    - tested as a compact species-side table
    - result:
      - table size is only about one byte per species
      - too small for normal evolution records
      - likely flags, indices, or another compact attribute table

- Sparse pair table at `0x1A32BDC`.
  - Assumption tested:
    - evolutions might be sparse rather than present for every species
    - a pointer/value pair table could index only species that actually evolve or have special evolution behavior
  - What was tried:
    - decoded the block as `413` pointer/value pairs
    - inspected the pointer destinations in `0x177xxxx`
    - checked whether the value field behaved like a species ID, method ID, item ID, or count
    - tried reading pointed data as simple evolution record lists
  - Result:
    - indices are continuous `0..412`, not obviously species IDs
    - pointed data does not parse cleanly as evolution records
    - candidate remains more plausible for egg moves, tutor data, or another sparse learnability system than for evolutions

- Species-ID cluster regions at `0x1A20B5A` and `0x1A3F65C`.
  - Assumption tested:
    - distinctive species such as Eevee might reveal an evolution table because they have many branches
  - What was tried:
    - searched for U16 sequences containing Eevee and its expected branch targets
    - checked for neighboring bytes/words that could represent methods, levels, or item IDs
    - repeated the same idea with Roselia, Piloswine, and Munchlax
  - Result:
    - both regions contain interesting species clusters
    - but the surrounding structure looks like list membership rather than full `source -> target by method` records
    - these regions are likely inputs to some other system, not the evolution table itself

- Sequential species list at `0x1A420F4`.
  - Assumption tested:
    - the region could be a base index into a larger evolution-related structure
  - Result:
    - it is just a plain sequential species-ID list
    - no attached parameters or record boundaries indicating evolutions

- Distinctive-case validation strategy that did not yet produce a usable anchor.
  - Cases repeatedly used:
    - Eevee for many branches
    - Roselia for stone evolution
    - Piloswine for unusual evolution logic
    - Munchlax for friendship evolution
    - starter lines for simple level evolution
  - Result:
    - these cases were useful for rejecting false positives
    - none of the currently identified candidate tables matched enough of them to confirm an evolution format

- Broad pointer-family hunting in the species-resource neighborhood.
  - Assumption tested:
    - evolutions might live behind another `1293` or `1294` pointer table near the solved species resources
  - What was tried:
    - scanned the broader `0x1900000..0x1B00000` area for arrays that resemble ROM pointers
    - prioritized tables whose size was close to the species count
    - spot-checked the pointed blocks for compact structured data
  - Result:
    - useful for finding the real level-up learnset table
    - did not yet reveal a second pointer family that behaves like evolution records

## Best Next Steps

1. Build a source-first extractor that reads:
   - `Base_Stats.c`
   - `Evolution Table.c`
   - `Learnsets.c`
   - `Pokemon_Name_Table.string`
   - `attack_name_table.string`
   - `ability_name_table.string`
2. Treat the bundled `.gba` as a verifier instead of the default data source.
3. Compare a few distinctive cases between source and ROM:
   - Eevee branches
   - Roselia evolution method
   - Piloswine -> Mamoswine
   - Munchlax friendship evolution
4. If source and ROM match for representative samples, remove the planner's hard dependency on the bundled `.gba`.
5. Keep ROM parsing only for categories that are not clearly represented in source:
   - graphics/assets
   - trainer party tables / difficulty variants
   - any Unbound-only runtime data not present in the source repos
