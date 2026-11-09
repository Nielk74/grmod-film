# WP2 — crop texture, pending camera and user decision

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim / real files:** the 27 JPEGs include two 28 mm / 6000 px, sixteen 35 mm / 4800 px and nine 50 mm / 3360 px images. AK000019–027 combine a 35 mm cropped JPEG with full-frame DNG DefaultCrop. Focal-length metadata resolves those files' crop identity; it does not establish all live processing descriptors, custom ratios or their exact firmware provenance.

**Source defect:** the former MTF guard required width ≥4096 and dimensions divisible by eight, directly rejecting 3360 px and several active sizes. Legacy grain at 3360/fullWidth 6000 has step 457, attenuation 143/256 and rounded Medium gain 35 instead of 64. A retained sensor crop should not inherit resize attenuation.

**Host implementation:** explicit `textureGeometry: 'sensor' | 'output'` enables revised modules. MTF accepts even 4:2:2 widths from 960, processing the 8-aligned interior without changing dimensions, tails or padding. Source/fixture 720 px screennails and 160 px thumbnails remain excluded. This was **not a live preview survey**: `research/gr3-210/wp2-audit/preview-sizes.json` contains 27 null size tags. Actual camera descriptor widths remain unknown.

Span is `max(width, height × 3/2)` before display rotation. Sensor policy uses the primary main span once per job; output policy uses 6000. Previews inherit that reference; invalid/missing/preview-sized primaries fall back to 6000. Grain and halo scale from that reference. MTF on sensor policy retains the 6000-frame response, including on a true resized XS. Omitted options preserve the frozen legacy modules/recipe behavior; GR IV stays there.

**Evidence:** native/reference fixtures cover 3360×2240, 3000×4000, 5332×4000, 4800×2700 and 960×1280, active tails/padding, descriptor/heap canaries, fallback and allocation failure. The separate pipeline probe covers 3,528 stash states and dispatch/allocation controls. These are emulated checks, not camera tests. [Implementation evidence](../../../research/gr3-210/wp2-implementation/) and [declared source manifest](WP2-MANIFEST.md).

The [host sheet](../../../research/gr3-210/wp2-visual/wp2-crop-texture-sheet.png) uses native Standard R0000027, fixed Portra colour and no halo, showing Legacy/Sensor/Output. It processes a 6000×384 strip and displays identical 900×256 source patches at 100%. Strip-derived seeds differ from full-frame seeds; it is not a camera 28/35/50 comparison.

**Fresh source proof:** the remediation rebuild in a new ignored directory yields exactly the sealed T-texture SHA-256 `631974813579e055a65f80c1558133acd7f27259edf2b4dcfb9dc052c2f21768`, 38,408,796 bytes, with pinned independent decoder agreement. [Rebuild verification](../../../research/gr3-210/review-remediation-01/rebuild-verification.json). Later source timestamps therefore did not invalidate this binary; the sealed file was not replaced.

**Next:** use the revised card's baseline then T-texture comparison at 28/35/50 mm, including edges. Add true crop-Off, 3:2 XS, expected 1920×1280; record actual dimensions, post-view and playback anomalies. T-texture replaces only Pro 400H with approved Gold, retains Soft Focus and requires all five reset steps.

**Adoption blocker:** dimensions cannot distinguish 4800/3360 true resizes from 35/50 mm crops; no per-shot provenance bit was established. XS now receives MTF built for 6000 px. Adoption waits for the user's decision after these tests; output remains an option.

**Kill / limit:** out-of-bounds writes, preview/main confusion or failed parity reject the candidate. Appearance is the user's choice. No physical camera result or aesthetic approval is claimed.
