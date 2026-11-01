# grmod-film

GR III / GR IIIx film library for [GR Mod](https://github.com/Maxwooow/Ricoh-GRMod): twenty films with their recipes, a
Teal Sky Hue row, a Grain Effect row, four Halation colours, End Screen pictures, and a preview on real GR III photographs.
For the GR III (firmware 2.10) and GR IIIx (1.60). Not a Ricoh product.

This repository is the GR Mod source (Maxwooow, GPL-2.0-only, imported unchanged at upstream commit `1f4216e`, 0.8.6) plus
the film work on top, in two commits you can read. GR Mod's own documentation is kept in
[docs/GR-MOD-README.md](docs/GR-MOD-README.md).

## What it adds

- **Film library** (`core/src/filmpack`): twenty films (ten Fujifilm simulations, four film stocks as Fujifilm recipes make
  them, OPPO Find X9's Primrose and Hasselblad colour, four creative looks), each a colour transform of the camera's
  Standard rendering, sampled into a `.cube` and fitted to GR III's film format (mean ΔE2000 0.3..3.0), with a code-drawn
  icon and a recipe. The app's "Choose a film" fills a film from it; "Use all 20 films" fills them all. The looks are
  interpretations of how the films are published and described, not measured profiles. List and character of each film:
  [examples/gr3x/film-pack/README.md](examples/gr3x/film-pack/README.md).
- **Recipes** (`core/src/fw/gr3x/film-recipe.ts`): where the camera's Sharpness, Clarity, Shading and Halation start for a
  film. The native module is `tools/gr3x/native/films.c` compiled with `-DFILM_DEFAULTS` (`tools/gr3x/gen_films_defaults.py`);
  a changed value in the camera is kept as always.
- **Teal Sky** (`core/src/color/sky.ts`): a film's Hue row, renamed Teal Sky, moves its skies toward teal (+1..+4) or blue
  (-1..-4) with nine tone records per film; the camera's own hue rotation stays neutral for films.
- **Grain** (`tools/grain/grain.c`, `core/src/color/grain.ts`): luminance film grain made at the JPEG step, per film Weak /
  Medium / Strong and Small / Large, or set in the camera with the **Grain Effect** row (Off / 1 / 2 / 3). The grain lattice is
  relative to the 6000-pixel picture, so the screennail and thumbnail match.
- **Film MTF** (`tools/filmmtf/filmmtf.c`, `core/src/color/filmmtf.ts`): a film's own sharpness, made at the JPEG step before the
  halation and the grain: Kodak's MTF curves per dye layer (a boost of 8..33 pixel structures, softer fine detail, the red layer
  softest) on the main picture, in strips so it needs a few megabytes. Portra 400 only for now (`FILM_MTF` in
  `examples/gr3x/film-pack-v3/build.ts`; its camera Sharpness and Clarity start at 0). About three times the grain's work per
  picture; checked against its TypeScript reference byte for byte in an emulator (`tools/filmmtf/check.py`), not tried on a camera.
- **Halation colours**: red, orange, gold and white, kept in the film's Toning byte with the Halation state
  (`core/src/fw/gr3x/halation-rows.ts`). The parameter screen sizes its list for a film's 12..13 lines.
- **Preview** (`ui`): films applied to genuine GR III JPEGs (`ui/src/assets/samples`) with colour, halation and grain, 1:1
  loupe; eight End Screen pictures (`ui/src/assets/endscreens`, "Add GR Mod's pictures").

## Status

| | |
|---|---|
| Grain Effect row, red / orange / gold / white Halation, Teal Sky Hue row | tried on a GR III 2.10 camera and working (2026-10-28) |
| Everything else here (recipes' starting values, the film fits, preview, End Screens) | checked by the emulator probes and the tests below, not separately tried on a camera |

Firmware is modified at your own risk. Keep a copy of the official file and of any file you flash; the camera's own update
procedure applies.

## Build and test

```
npm ci
npm test            # core tests (vitest)
npm run build       # the desktop UI
```

The tests that open firmware need Ricoh's official files, which are not in this repository: set `GRMOD_GR3_FIRMWARE`
(`fwdc239b.bin`, GR III 2.10) and `GRMOD_GR3X_FIRMWARE` (`fwdc243b.bin`, GR IIIx 1.60); without them those tests are skipped.
With both: 259 passed, 141 skipped (other fixtures), 0 failed.

Film-specific checks: `tools/grain/check.py` (the grain ARM module in Unicorn against a Python reference, byte for byte;
`core/test/grain.test.ts` ties the TypeScript reference to it), `tools/gr3x/films_probe.py`, `halation_rows_probe.py`,
`teal_hue_probe.py` and `picture_stage_probe.py` (inputs from `tools/gr3x/probe-inputs.ts`), `core/test/film-recipes.test.ts`,
`core/test/teal-sky.test.ts`. A film-pack firmware from the command line: `examples/gr3x/film-pack`.

## Not in this repository

Ricoh's firmware files, and any experimental on-camera interface work.

## Credits and licences

- GR Mod by Maxwooow and contributors (GPL-2.0-only): https://github.com/Maxwooow/Ricoh-GRMod. This repository keeps its
  licence and notices; the full history is there.
- Sample photographs (`ui/src/assets/samples`): genuine RICOH GR III JPEGs, CC BY-SA 4.0, Wikimedia Commons (Stephan van
  Helden) and two by this repository's author; credits in `ui/src/assets/samples/CREDITS.md`. They are not covered by the code's
  licence.
- The End Screen pictures are drawn in code (`examples/gr3x/film-pack/Pictures.cs`).
