# Review of GR3_EXPLORATION_REPORT.md: directions, priorities and ideas

Reviewed 2026-11-09. Subject: `C:/Users/Antoine/.codex/worktrees/3840/grmod-film/docs/GR3_EXPLORATION_REPORT.md` (88 entries, 36,078 words).
Audience: the agent continuing this research. Treat this file as your new brief. It overrides the report's Live research index.

## 1. Verdict

The report is careful and honest, and its reverse engineering is useful. As a research programme it has drifted. It has a lot of evidence and very few decisions.

- **Nothing reached the camera.** Across 88 entries, no new idea was tested on a GR III. Almost every entry ends with "needs hardware". Static tracing has reached the point of diminishing returns.
- **The effort is pointed away from the project focus.** `CLAUDE.md` asks for Portra 400, CineStill and Gold, and for global colour axes. Autofocus takes 42.4% of the words. Colour-fidelity entries take 6.3%. The AF work was requested by the user, so it is legitimate, but it has produced no improvement and no measured baseline.
- **It ignores what the user has actually accepted.** The user rejected every Portra hue tweak. They called the film MTF "excellent", approved Gold's +2 EV negative exposure with compensated print, and said "grain still can be improved". The report continues none of these three threads properly.
- **It misses how the camera is really used.** 25 of the 27 photos in its own corpus are 35mm or 50mm crops. Texture is weakest or possibly absent in exactly those modes (section 3).

## 2. Rules for this next round

1. **Do not change Portra 400's colour** in `core/src/filmpack/looks.ts` or `examples/gr3x/film-pack-v3` unless the user names the change. Any Portra colour idea must be an extra slot or a side-by-side, and the user picks. Non-colour axes are welcome.
2. **Judge by the user's eye on real photos.** A lower ΔE against a model did not persuade them before. Metrics can rule things out, but they cannot approve a change.
3. **You prepare hardware tests and the user flashes.** Do not flash or write to a device. Each test ships with a short test card in the style of `docs/GR3_HDF_210_TEST.txt`.
4. **Settings survive flashes.** Every test build must contain the film pack's looks, ratios and guard. If it cannot, its notes must include the section 5 reset steps of `docs/GR3_HDF_210_TEST.txt`. A build without them very likely left the camera stuck on 2026-11-05.
5. **Stay on 2.10.** Going to 2.20 cannot be reversed.
6. **Every direction needs a kill criterion.** Write it before the work starts, and stop when it is met.
7. **Case counts are not results.** Report what a test rules in or out.

## 3. What I checked, and corrections to make

I read all 88 entries. I checked the items below against the repo, the RTOS and the photos in `C:\Users\Antoine\Pictures\Ricoh2`. I did not re-run the report's probes or the test suite, so its other numbers are unaudited.

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| C1 | **JPEG tables vary per image.** The 27 JPEGs use 23 distinct DQT sets, including at the same size and ISO. IMG-011 and ORCH-009 use two of them and call them "exact GR III 2.10 JPEG tables". | Pillow `quantization` over all 27 files | Those results are two samples of a varying process. The pattern looks like per-image rate control (mechanism not established). See WP9. |
| C2 | **CRE-014 and IMG-013's "crop versus resize unresolved" can be closed.** AK000019..27 record FocalLengthIn35mmFilm = 35, with a 4800×3200 JPEG and a 6000×4000 DNG crop. | Exif tag 0xA405 on every file | These are 35mm crops, not M-size resizes. |
| C3 | **CRE-003 is too cautious about the full-frame DNG hook.** Those nine files show the hook's behaviour on real hardware: cropped JPEG, full DNG. AK000001..18 keep DNG crop equal to JPEG crop. | C2 plus the CRE-003 crop groups | A natural with-hook and without-hook sample exists. Custom-ratio capture remains unvalidated. |
| C4 | **Film MTF is rejected at the 50mm crop, by the guard alone.** `filmMtfApplies` requires width ≥ 4096, and 3360×2240 fails. 9 of 27 photos are this size. IMG-007's whole-buffer descriptor may rescue it, but that is unproven. | `core/src/color/filmmtf.ts:32,62` | The feature the user liked most may be missing from a third of this corpus. See WP2. |
| C5 | **Grain weakens in crops.** Amplitude is 0.797× at 4800, 0.664× at 4000 and 0.559× at 3360 (`att = 65536 / step`). IMG-008 never tested 3360 and declines to call this a bug, but a crop is not a resize and needs no resize attenuation. | `core/src/color/grain.ts:57-58` | See WP2. |
| C6 | **The report's Gold is not the approved Gold.** Commit `67881cd` (approved +2 EV negative, +1.141733 EV print) exists only on `film-research`. The report's worktree lacks it, and `film-research` lacks main's MTF commits. | `git log` both ways | No Gold number in the report describes the approved look. See WP1. |
| C7 | **Fit numbers are not comparable across entries.** ORCH-006/007 use base library fits. CRE-016 uses `post:true` at 33³ (Portra p95 2.979). IMG-003 uses v3 with end-grey weight and shoulder (Portra p95 4.972). | The entries themselves | Fix one reference transform set. |
| C8 | **ORCH-005 misses the obvious inference.** All 26 factory styles share one block, and 59 of its 60 groups are identity. The stage may simply be inactive, so "does it change pixels at all?" comes before any semantics. The count of 60 does equal 12 × 5 from `core/src/color/hue.ts:5`. | ORCH-005 and `hue.ts` | See WP3. |
| C9 | **The Live index contradicts the synthesis.** AF is rated High, while ORCH-010 says there is no demonstrated improvement and fixed-threshold relaxation is not selected. AF-007 and AF-010 are negative for scan range. | The report itself | Replaced by section 4. |
| C10 | **Evidence is fragile.** There are 63 references to `%TEMP%` paths. The folders and both snapshot zips exist today, but a temp cleanup would break most reproduction commands, and the zips store absolute source paths. | Direct check | See WP1. |
| C11 | **Text corruption.** 436 tokens have digits glued to words ("at32", "Portra6.760"), mostly in IMG entries. They break search. | Regex count | See WP1. |

## 4. New priorities

| Priority | Work package | Effort | Why |
|---|---|---|---|
| P0 | WP1 Clean base and readable index | S | Everything else depends on it |
| P0 | WP2 Crop-mode texture | S to M | Largest user-visible gain for the effort |
| P0 | WP3 Multi-axis go or no-go, one hardware test | M | The only path to colour-selective control |
| P1 | WP4 Exposure latitude axis | M | The one colour axis the user has approved |
| P1 | WP5 Per-stock MTF | M | Extends what the user called excellent |
| P1 | WP6 Grain programme | M | The user asked for it |
| P1 | WP7 White balance as part of the film | S to M | Unexplored, can be tested today without firmware |
| P1 | WP8 Close the loop, model against camera | S to M | No entry measures it |
| P1 | WP9 JPEG rate control against grain | S | Cheap, and could change the grain conclusions |
| P2 | WP10 AF: measure or freeze | S to M | Needs a baseline and a target |
| P2 | WP11 Snap focus upgrades | S | Better focusing without touching AF |
| P2 | WP12 Small product wins | S each | Low risk |
| Frozen | Section 7 | | Do not continue without a new reason |

## 5. Work packages

### WP1. Clean base and readable index

- Rebase the research on one tree that contains both main's MTF commits and `67881cd`. Record the commit SHA in every future entry.
- Define one reference transform set: the exact v3 build recipes, with approved Gold as a separate named entry. Re-run only the results you still rely on (IMG-003, ORCH-006).
- Move scripts and results from `%TEMP%` into a stable folder with relative paths. Keep it git-ignored if it must hold firmware-derived data.
- Replace the single 285 KB file with:
  - an index of at most 150 lines: decisions, status, next step, kill criterion;
  - one file per topic;
  - `tools/gr3x/symbols-gr3-210.json` holding each address, name, confidence and evidence class. The addresses are the report's most reusable asset, and they should not live in prose.
- Mark superseded entries in place. AF-002 is corrected by AF-004, CRE-003 by CRE-014, UI-011 by UI-015, and AF-UI-004 by AF-UI-005.
- Use a fixed entry format: claim, evidence class (source, emulated, real file, hardware), decision, next step, kill criterion. Limitations go in one line. Remove tool chatter (REA provider status, Impeccable). Fix the glued numbers.

**Done when** a new reader can state the top five actions from the index alone.

### WP2. Crop-mode texture (do first)

The user shoots crops, and physically a crop enlarges the negative, so grain and halation should stay anchored to the sensor.

1. **MTF.** Lower `FILM_MTF_MIN_WIDTH` so that 3360 passes, in both `core/src/color/filmmtf.ts` and `tools/filmmtf/filmmtf.c`, keeping thumbnails and small previews excluded. Check every descriptor width the camera passes first.
2. **Non-8-aligned sizes.** Support 5332×4000, 3000×4000 and 4800×2700 by processing the aligned area instead of rejecting the frame.
3. **Grain and halation, aspect-only crops.** Use `span = max(w, h × 3/2)` in place of width. This corrects square, 4:3, 5:4 and portrait with no provenance at all: 4000×4000 gives 6000. No entry proposes this. IMG-008 only concludes that width is insufficient.
4. **Grain and halation, 35mm and 50mm crops.** These need one bit: crop or resize. Read the crop mode per exposure, the same way the date stamp reads orientation (`core/src/fw/gr3x/datestamp.ts:223-267`). If that fails, default to sensor-anchored, since none of the 27 photos is a resize.
5. Put all of it in the test build of section 6. Show the user the same subject at 28, 35 and 50mm, old against new.

**Kill or keep:** the user's choice. Keep output-relative scaling as an option if they prefer it.

### WP3. Multi-axis colour: one decisive test

`CLAUDE.md` says colour-selective change needs the hue stage. `build.ts:58-59` notes that skin cannot be capped by a global fit. This should not sit at the bottom of the list as "Research".

Use the film slots as probes, and on-camera RAW development to get perfect registration. Shoot **one DNG** of a hue and luminance chart, then develop it through each probe slot.

| Slot | Block contents | Question |
|---|---|---|
| A | Standard's block | Control |
| B | All 60 groups strongly perturbed | Does the stage touch pixels at all? |
| C to H | Group g perturbed if bit k of g is set | Six slots give each pixel a 6-bit code naming its group |
| I to K | Row-sum scaling (0.5, 0.75, 1.25) | Scale semantics and clipping |
| L | Group 0 alone, row sums changed | What the odd 512 group is |
| M, N | Neighbouring sectors with different perturbations, on a smooth hue ramp | Interpolation across boundaries |

Then decode the JPEG differences into a table of hue sector, luminance band and order in the pipeline. Port the fitter only after that.

**Kill:** if B matches A, record that the stage is inactive and close the direction.
**First use if it works:** Gold's and Kodachrome's skin, CineStill's teal against red. Portra only by the user's pick.

### WP4. Exposure latitude

The approved Gold result is the strongest colour signal available, and the report does not use it.

- Bring `tools/jpeg_experiments/exposure_print` to the working tree and build approved Gold as an **extra slot** beside current Gold.
- Apply the same negative-exposure and print-compensation sweep to CineStill. Show Portra at +1 and +2 EV as an opt-in side-by-side only.
- Explore a per-film exposure bias, the digital version of rating Portra at EI 200. Trace whether AE compensation can follow the selected film. A shoulder alone does not reproduce this.
- Consider ISO as push and pull: a curve family selected by shot ISO. This needs IMG-012's job-bound ISO first.
- **Licence check before shipping.** The derived assets are CC BY-SA 4.0 and the repo is GPL-2.0-only. Ask the user how they want this handled.

### WP5. Per-stock MTF

`build.ts:65-68` gives every film Portra's curves because Portra is "the only stock measured here".

- Digitise the published MTF curves for Gold 200 and Vision3 500T (the existing CineStill proxy). Keep Portra's as it is.
- Compare at equal luma response, on real photos, after the full chain. Drop the 25%-chroma and scalar variants (IMG-001, IMG-005). They showed a subtle effect only.
- Expose MTF in the desktop builder and preview (WP12).

**Kill:** the user sees no difference from Portra's curves at 100%.

### WP6. Grain programme

The report tested block overlap and an Auto budget. Neither is what makes grain look more like film.

- Give each stock its own character, not just amount and size: tone dependence, luma-to-chroma ratio, and clump size distribution. v3 uses Print Grain Index only to raise Portra by one step (`build.ts:93-97`). Use published granularity data for all three focus films.
- Fix high-ISO mottling, the problem IMG-013 left unsolved. Try a chroma-only low-pass in the JPEG hook before grain, and a per-film noise reduction default. Scaling grain cannot remove mottling already in the image.
- Show A/B sheets at 100% on the user's own photos, including ISO 5000 (AK000019..24).

**Kill:** two rounds with no preferred variant.

### WP7. White balance is part of the film

No entry traces white balance, and the film recipe's ten bytes do not include it. CineStill is a tungsten stock, yet AWB normalises the illuminant before the film transform runs. This may remove more of its identity than any curve can restore. The RTOS holds a rich WB system (`CWhiteBalanceColorTemperature`, `CWhiteBalanceLightSourceDetector`, `ConvertFilterWhiteBalanceGain`, `GetUserSettingWhiteBalanceColorTemp`).

1. **No firmware needed.** Develop mixed-light DNGs on the camera through CineStill at AWB, at 3200K and at 4300K. Do the same for Gold and Portra at AWB against fixed daylight. The user compares.
2. If a fixed WB wins, add a per-film WB policy that is applied on film selection and restored on leaving it.
3. Only then consider IMG-004's illuminant-conditioned fits. Those are much more work.

**Kill:** the user prefers AWB in the first step.

### WP8. Close the loop

Every colour number in the report is model against target. None is model against a camera JPEG.

- On the camera, develop a few of the 27 DNGs to Standard and to each focus film, texture off. Registration is perfect and no new shots are needed.
- Predict each film JPEG from the Standard JPEG with the stored coefficients. Plot the residual by hue and luminance.
- Check `calibration.json` and its "37-pair study" on `film-research` first, so this does not repeat it.
- If the residual is larger than the fit error, then improving the fit is pointless until the ISP model is fixed.
- **For real fidelity,** ask the user whether they would shoot one roll each of Portra and Gold beside the GR III, with a chart, lab scanned. Until then, say "fits the model" and never "matches the film". Reuse the existing before-and-after viewer (`portra-compare`) for blind comparisons.

### WP9. JPEG rate control against grain

On the camera, develop one DNG with grain Off, Low, Medium and High, and with halation on and off. Compare DQT tables and file sizes.

If grain coarsens the tables, grain costs detail across the whole image, and strength limits should account for that. It would also explain why ORCH-009's chroma retention moves between 0.68 and 0.88. Only then trace the native table selection.

### WP10. Autofocus: measure or freeze

The report has no baseline and never names the failure it wants to fix. Ask the user which of these actually hurts: low-light hunting, macro, wrong target, or speed.

1. **Baseline on stock behaviour, no firmware.** Use fixed targets and fixed lens start positions, and film the LCD and lens with a phone at high frame rate. Log the error rate from sharpness on the results.
2. **Passive trace build, only if step 1 shows a problem worth solving.** Hook setup `0x53426720`, capture `0x53428380` and the result path. Store a compact summary **in each photo's metadata**, next to the known AFInfo tag constructor (`0x535d3418`), or a RAM ring dumped to file. A per-photo trace avoids new file I/O paths.
3. **Scan range.** Stop static tracing. Link the hidden dialog (`0x02000064`) in a test build and try AF on a 30cm subject at 50cm-to-infinity. One test answers what AF-007 and AF-010 could not.

**Kill:** no named failure from the user, or step 1 shows stock AF is acceptable. Freeze all AF tracing and keep only the symbol map.

### WP11. Snap focus upgrades

For street shooting, this may improve focus results more than any AF change.

- The eight Snap distances are one native table at `0x53b591e0` (AF-UI-001). Try better values, and first find how labels are drawn.
- Add a **Hyperfocal** entry that follows the aperture, reusing ORCH-003/004's verified DOF formula. At 21 µm: f/2.8 5.7m, f/4 4.0m, f/5.6 2.8m, f/8 2.0m, f/11 1.45m. This gives the DOF research a real use.

### WP12. Small product wins

- **Provenance in one patch.** Add a short build tag to the EXIF `Software` string (CRE-003 notes that it cannot tell stock from patched). Check readers that depend on it. Pair it with the host archive from CRE-011.
- **Desktop MTF.** MTF is only reachable from the v3 CLI. Add a builder option and include it in the preview (`ui/src/pages.tsx:65-78`).
- **ADJ Grain.** The 404-byte candidate is ready. Include it in the test build if it does not cost Soft Focus, or make that an explicit build choice. Leave bypass out for now.
- **Film order.** Ship reordering, which UI-014 shows captures most of the benefit. Drop the dynamic favorites hook for now.
- **Status label `G2 H1 gold`** (UI-005). Consider it after the above.

## 6. One hardware session

Bundle tests to minimise flashes, and give the user a single test card.

- **Build T-colour:** the WP3 probe slots. For development only, not for shooting.
- **Build T-texture:** the current pack plus WP2, approved Gold, ADJ Grain, and any WP11 table change.
- **No build needed:** WP7 step 1, WP8, WP9 and the stock half of WP10.
- The card lists the exact shots, settings and files to bring back, plus the return path to the current pack. The agent then does all the analysis.

## 7. Freeze or drop

| Item | Entries | Reason |
|---|---|---|
| Grain block overlap | IMG-010, IMG-011 | The report's own visual review found no real benefit |
| Simulated focus metrics | AF-IMG-002 | Gaussian-blur proxy, not related to the camera's AF path |
| Temporary Select AF | AF-UI-004 | Stock feature, as AF-UI-005 shows |
| AF threshold, predictor and lens tuning | AF-003 to AF-006 | No measurement and no target. Keep only as map data |
| Hidden scan range tracing | AF-007, AF-010 | Replaced by the one hardware test in WP10 |
| Histogram ROI and percentage overlay | UI-007 to UI-010 | No producer found, no overlay path, and no link to film work |
| DOF criterion display | ORCH-003, ORCH-004 | Reused through WP11 instead |
| Orientation AF-point memory | AF-ORCH-007 | No owner or event contract. Revisit on user request |
| Navigation step model | UI-014 | Answered: reorder |
| Multi-exposure effect order | CRE-006 to CRE-008 | Niche, and the job path is unknown |
| On-camera three-film audition queue | CRE-012, 013, 015 | High risk. The desktop already does this at near-zero cost (CRE-016) |
| Full-sensor reframing on camera | CRE-002 | The DNG already keeps the frame, so a desktop converter can do this. Medium at best |
| Luma-only Auto grain | IMG-013 | Negative result. WP6 covers the actual problem |
| Halation excitation lookup | ORCH-006, ORCH-007 | Pause until one night-photo A/B on exact v3 shows the user cares |
| Selected-frame histogram and guides | CRE-004, UI-008 | Pause. Nice but unrelated to the focus |

## 8. Order of work

1. WP1, then WP2 on the host.
2. Start WP7 step 1, WP8 and WP9 together, since they share one camera session of RAW development.
3. Prepare the two test builds and the card (section 6). The user flashes.
4. Decide WP3 from the result. Run WP4, WP5 and WP6 in parallel, with one A/B sheet per round for the user.
5. Ask the user the WP10 question. Then do WP11 and WP12.

Report back with at most one page per round: what changed, what the user must look at, and what was killed.
