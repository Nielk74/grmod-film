# GR III 2.10 — one camera session

**Host checked; camera operation remains untested.** The human operator performs every camera/card operation. Stay on **2.10**. Back up photos/settings, use a full battery and keep official 2.10 available. Never save probes or added ratios to **U1/U2/U3**. If operation is abnormal, stop and use the reset/return guidance; retain the observed symptoms and last installed hash.

Sequence: **1 baseline → 2 reset → 3 T-texture → 4 reset → 5 T-colour, including colour/WB developments → 6 reset → 7 return.** This keeps the same three normal firmware changes. The optional verified-baseline installation in section 1 still adds one change, as before.

Each folder has its own `fwdc239b.bin`; use only that folder's file.

| Folder | SHA-256 |
|---|---|
| T-texture | `631974813579e055a65f80c1558133acd7f27259edf2b4dcfb9dc052c2f21768` |
| T-colour | `d761ea15d50aeaecee0d08e44e63a00cb4dc0899a405c89fd5e8afd988502283` |
| Return-current-MTF | `cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55` |

**Library and return choices.** T-texture has twenty films: approved Gold replaces Pro 400H in slot 64; the other nineteen colours, including current Gold and Portra, remain exact. Soft Focus stays; ADJ Grain replacement is omitted. T-colour has six comparators and fourteen diagnostic probes, with all textures disabled. Both retain ratios and the R10 settings guard. **Return-current-MTF has no shot animation.** If the camera last ran a film-pack animation variant from `tools/shot-animation/out` in the primary checkout, this return pack is not that starting state. Record/preserve the actual starting file/hash and accept this difference before beginning; installation identity is otherwise **unknown**.

**Common controls.** RAW+JPEG, sRGB, 3:2, JPEG Recorded Pixels **L** unless a test explicitly changes it. L is size, not a separate JPEG-quality setting. Keep native encoding unchanged. Fix manual exposure, ISO, focus, WB/fine adjustment, NR and corrections within each comparison; log unavailable controls. For chart/model developments set native colour sliders, Sharpness/Clarity and RAW exposure adjustment to 0. HDF, timestamp and Soft Focus Off. Return originals without resizing or recompression.

## 1 — Baseline before changing firmware

Log the installed file/hash, or unknown. With Portra, Sharpness/Clarity 0 and grain 2/small, capture the same static target at **28/35/50 mm**, halation Off and then strength 1/gold: six RAW+JPEG frames. Include detail, flat midtones and a bright highlight. Lock position, focus, light and exposure; do section 3 immediately after the intervening reset/install, before changing the scene. Unknown installed identity makes the baseline contextual. For an exact known pack baseline, first perform the full section 2 reset and install Return-current-MTF; this optional extra change also removes any animation variant.

Capture one evenly lit colour/grey-chart DNG in native Standard, with unclipped hue patches at several brightness levels and ideally a smooth hue ramp. Keep it for section 5; T-colour normally develops existing DNGs.

## 2 — Full reset before T-texture

Use this complete procedure again in sections **4 and 6**. Translation of `docs/GR3_HDF_210_TEST.txt`, section 5: settings survive firmware changes and stock firmware does not recognise added values.

1. Aspect ratio **3:2**.
2. Image Control a factory item such as **Standard**; Clarity **0**.
3. Timestamp **Off**; End Screen Picture **Original**. Before a reduced/different film library, replace added films in U1/U2/U3 with factory styles or re-save those modes. Historical mod revision steps 12+ → 11 or earlier restart older film/halation records from current values. For historical steps 13+ → 12 or earlier, first choose one of the first two timestamp styles, set Follow Camera Orientation On, then timestamp Off. Changed presets restart at defaults. With no-film firmware, an active film becomes Standard but keeps its parameter values; restore those manually. These historical revision numbers are not this card's section numbers.
4. **Settings → Reset → Restore Default Settings**.
5. Only then install the intended verified test/return file or official `fwdc239b.bin`. The app's stock-firmware action also requires reset confirmation. T6d's separate film records are ignored by stock and may remain.

## 3 — T-texture, while baseline lighting still matches

Install T-texture after section 2, recheck the common controls and repeat section 1's six Portra frames. Inspect both sets at **100%**: grain/clumps, detail, highlight-halo width and preview/capture consistency. Add **4:3/L** and **16:9/M** frames; inspect the last four columns/rows for boundaries. No current film colour was retuned.

Add **one true resized XS frame**: crop Off/28 mm, 3:2, JPEG Recorded Pixels **XS**, expected **1920 × 1280**. Log actual dimensions. Check **post-view and playback** for corruption, bands, stalls or other anomalies on this and the main frames. The MTF width floor changed from 4096 to 960; live descriptor widths are still unmeasured. Surveyed 720/160 previews are source/fixture evidence, not measurements from these files.

Sensor policy assumes retained sensor pixel pitch. It cannot distinguish 4800/3360 true resizes from 35/50 mm crops; XS also receives MTF designed for the 6000 px frame. **These are adoption limits for the user to judge**, not a claim that every size is correct.

**WP9 grain alternative — capture route.** The custom Grain row is not exposed on the film RAW-development page, so no same-DNG four-way control is established. Without another firmware, use T-texture: one film, tripod/static scene, L/28 mm, fixed manual/common controls, **Halation Off**, fixed grain size, then **Grain Off/1 (Low)/2 (Medium)/3 (High)**: four RAW+JPEG captures. Record each setting/output. Fresh sensor noise, registration and per-image codec variation limit causal attribution. Do not substitute an unverified shooting-setting→RAW-reopen gesture. The combined eight-way same-DNG halation matrix remains deferred.

Source basis: `films-r10.ts:340–343` uses Standard's RAW parameter lines; `halation-rows.ts:126–134` excludes custom kinds 10/11/15 there. The shooting Grain row is kind 11 (`halation-rows.ts:29–40,208–240`); `films.c:339–343` preserves halation when changing grain.

## 4 — Full reset before T-colour

Repeat **all five items in section 2**, then install T-colour. Do not put a probe in U1/U2/U3.

## 5 — T-colour: RAW route, conditional capture route, colour/WB

Recheck common controls. Playback → Image Edit → RAW Development: select the chart's **original DNG** and develop **native Standard, MA A control, MA B all, MA A again**. Log every filename/slot/settings. Grain/MTF/date/ADJ Soft Focus modules are absent; all twenty halation gains are zero regardless of RAW settings. Use Continue or reselect the original DNG, never a previous JPEG.

If B differs from the repeated A control, develop **C–N** from that DNG: C–H group-index bits, I–K scales, L group 0, M/N adjacent-index hypotheses. If B appears to match A, retain all four outputs and add the requested **one tripod RAW+JPEG capture on A and one on B**, with fixed scene/light/exposure/ISO/focus/WB. No extra flash; never save probes to U1/U2/U3. Repo review found no capture-specific technical safety reason for the earlier blanket ban; this is a narrowly requested, still hardware-untested diagnostic pair, not normal probe shooting. Stop on operational anomalies.

Label **RAW-development route** and **capture route** separately. A negative RAW result alone does not establish capture inactivity. Root compares decoded pixels, repeated-A/DQT variation and capture noise/registration before stating what each tested route rules out; no global inactivity claim from one route.

Retained IDs: **64 Portra, 65 CineStill, 66 current Gold, 67 approved Gold, 68 Kodachrome, 69 Astia**. A–N are **70–83**. The general app deliberately reports T-colour unrecognised/unverified; its separate diagnostic verifier covers it. Never enable a general-app write bypass.

**Matched model/WB developments, still on T-colour.** Use up to three existing DNGs: daylight skin/sky, mixed light and high-ISO shadows. At identical Daylight WB/common controls develop each to **native Standard, Portra, CineStill, current Gold, approved Gold**. For mixed light add CineStill **AWB/3200 K/4300 K**, and Portra/current Gold **AWB**; reuse Daylight outputs. Match fine adjustment, record exact AWB mode and recheck controls inherited from capture. These registered outputs test model/WB, not real-film fidelity.

## 6 — Full reset before return

Repeat **all five items in section 2** before the return installation. Never recall a saved probe mode.

## 7 — Return and bring back the files

Install **Return-current-MTF**, reapply ordinary settings manually and confirm normal operation. Its hash is the table above; **it has no shot animation and may differ from the pre-session build**.

Keep every original DNG, capture JPEG and developed JPEG. Log `build; route; source DNG; output JPEG; slot/name; crop/pixels; WB/fine adjustment; grain/size; halation/colour; MTF; other settings/deviations`, plus actual order, post-view/playback problems and 100% preferences. EXIF Software and filename order do not prove build identity. Return the starting-build identity/unknown declaration with these files.

RAW workflow: [official GR III manual](https://www.ricoh-imaging.co.jp/english/support/man-pdf/gr-3.pdf), pp. 100–101. Continue: [official firmware history](https://www.ricoh-imaging.co.jp/english/support/digital/gr3_s.html). The full local reset note remains authoritative for mod-version compatibility.
