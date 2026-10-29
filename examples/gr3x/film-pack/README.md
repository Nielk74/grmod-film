# GR III film pack

A GR III 2.10 firmware (GR IIIx 1.60 builds the same way) with twenty films and their recipes
(where the camera's Sharpness, Clarity and Halation start, and each film's grain), eight End Screen
pictures, soft focus on the ADJ lever and the date imprint, built with GR Mod's round 10 and the
camera-tested default ratio menu. The films are GR Mod's film library (`core/src/filmpack`), which
the app offers too ("Choose a film", "Use all 20 films").

The films are colour transforms of the camera's Standard rendering, written in `looks.ts`. Each one
is sampled into a 33-point `.cube` and fitted to GR III's film format (matrix, three curves, second
matrix) by GR Mod's own fitter. `build.ts` prints the fit error (ΔE2000) of every film. The
Fujifilm simulations, film stocks and OPPO looks are interpretations of how they are published and
described. They are not measured profiles.

| # | Film | Character |
|---|------|-----------|
| 1 | Velvia | Landscape slide film: deep blue skies, lush greens, magenta-leaning reds, dense shadows |
| 2 | Astia | Soft slide film: vivid blues and greens over a gentle tonal scale, flattering skin |
| 3 | Classic Chrome | Documentary colour: muted, cyan skies, olive greens, hard shadows |
| 4 | Classic Neg | Superia-style negative: hard contrast, teal shadows, warm highlights, rosy reds |
| 5 | Nostalgic Neg | 1970s American colour: amber highlights, rich shadows |
| 6 | Pro Neg Hi | Portrait negative with a little punch |
| 7 | Pro Neg Std | Studio portrait: very soft, low saturation, smooth skin |
| 8 | Eterna | Motion picture film: flat, lifted, teal shadows, warm skin |
| 9 | Acros | Fine-grain black and white |
| 10 | Acros Red | Acros through a red filter: dark skies, luminous skin |
| 11 | Kodachrome 64 | Iconic reds, dense blues, warm and contrasty |
| 12 | Portra 400 | Creamy highlights, glowing skin, pastel greens and blues |
| 13 | Gold 200 | Golden summer consumer film |
| 14 | CineStill 800T | Tungsten night film: teal shadows, glowing reds (starts with Halation Medium, red) |
| 15 | Primrose | OPPO Find X9's Portra-inspired filter: warm soft shadows, pleasant greens |
| 16 | Hasselblad Std | Hasselblad natural colour as OPPO tunes it: true hues, soft roll-off, open shadows |
| 17 | Aerochrome | False-colour infrared: foliage crimson, skies cyan-blue |
| 18 | Instant | Instant film: milky blacks, creamy highlights, cyan shadows |
| 19 | Blockbuster | Teal and orange grade |
| 20 | Platinum | Split-toned black and white: cool shadows, warm highlights |

End Screen pictures (Setup › End Screen › Picture): Star Trails, Film Strip, Contours, Aperture,
Synthwave, Bauhaus, Great Wave, Good Night. They are drawn in code (`Pictures.cs`).

## Build

Windows, from the repository root, with the official `fwdc239b.bin` (SHA-256 `d6a3c9c2…54bfd4`):

    powershell -File examples/gr3x/film-pack/pictures.ps1 examples/gr3x/film-pack/out/pictures
    npx vite-node examples/gr3x/film-pack/build.ts PATH/TO/official/fwdc239b.bin examples/gr3x/film-pack/out

`out/` gets the firmware, `SHA256SUMS.txt`, the films as `.cube` files (they also load in GR Mod's
UI, one per film slot), `fit-report.json`, the icon sheet and the pictures as the camera will
decode them. The build only writes the firmware after GR Mod's self-check passes and a fresh engine
rebuilds the same bytes from the recipe stored in the file.

`preview.ts` draws a contact sheet of the fitted films on your own photos. `photos.ps1` turns JPEGs
into its input and `bgr2img.ps1` turns its output into a JPEG.

## Install

The steps are the same as GR Mod's (see `docs/GR3_HDF_210_TEST.txt`). Charge the battery fully and
copy `fwdc239b.bin` to the root of the card. Hold MENU while switching on, choose Execute, and
press OK. Do not update the camera to 2.20: it cannot come back to 2.10.

Flashing the official 2.10 file restores the camera. Reset the settings first (Setup › Reset)
whenever you go back. The films are in Image Control, and each one has its own parameters and
a Halation row.
