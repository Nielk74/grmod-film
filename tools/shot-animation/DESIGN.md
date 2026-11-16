---
name: Shutter studies
description: A warm inspection bench for an enthusiastic neon CRT mascot.
colors:
  paper: "#f5f2e9"
  ink: "#25312f"
  vermilion: "#af4932"
  quiet: "#62695f"
  rule: "#cdcdbd"
  preview: "#e8e7dd"
  button-cream: "#fff1d6"
  button-hover: "#3e534a"
  active-green: "#38604a"
  active-paper: "#d9e4d2"
  camera-case: "#252729"
  lcd-dark: "#1a231e"
  lcd-cream: "#fff8e7"
  phosphor: "#9bff19"
  flash: "#d5ff5b"
  glass: "#061b12"
  portal-depth: "#103d25"
  portal-rim: "#112c20"
  orange: "#ff510a"
  lemon: "#fff52b"
  hot: "#f3ffed"
  magenta: "#ff39d4"
  ivory: "#fff0d2"
  sprite-ink: "#20251f"
  sprite-shadow: "#303a2c"
typography:
  display:
    fontFamily: "Barlow, Arial, sans-serif"
    fontSize: "76px"
    fontWeight: 600
    lineHeight: 0.99
    letterSpacing: "-2.1px"
  title:
    fontFamily: "Barlow, Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    letterSpacing: "-0.25px"
  body:
    fontFamily: "Arial, sans-serif"
    fontSize: "15px"
    lineHeight: 1.65
  caption:
    fontFamily: "Arial, sans-serif"
    fontSize: "13px"
    lineHeight: 1.65
  action:
    fontFamily: "Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 700
  inspection:
    fontFamily: "Arial, sans-serif"
    fontSize: "12px"
  supporting:
    fontFamily: "Arial, sans-serif"
    fontSize: "11px"
rounded:
  lcd: "3px"
  replay: "5px"
  button: "6px"
  surface: "12px"
spacing:
  tight: "8px"
  item: "12px"
  control: "18px"
  preview-bottom: "20px"
  column: "32px"
  page: "52px"
components:
  button-shutter:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.button-cream}"
    typography: "{typography.action}"
    rounded: "{rounded.button}"
    padding: "13px 17px"
  button-shutter-hover:
    backgroundColor: "{colors.button-hover}"
  button-replay:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.button-cream}"
    rounded: "{rounded.replay}"
    padding: "12px 16px"
  preview-stage:
    backgroundColor: "{colors.preview}"
    rounded: "{rounded.surface}"
    height: "284px"
  camera-shell:
    backgroundColor: "{colors.camera-case}"
    rounded: "{rounded.surface}"
    padding: "12px 12px 0"
---

# Design System: Shutter studies

## Overview

**Creative North Star: "A small CRT with excessive enthusiasm"**

The original charcoal CRT, crooked antenna, ivory gloves, orange sneakers and tiny photograph carry the expression. Its ink outlines and raster geometry remain the visual identity. Acid-lime phosphor and saturated geometric effects make its actions readable against both a quiet review stage and a photograph.

The inspection page is warm, spare and orderly: condensed display lettering, dark green-black text, ruled controls and restrained vermilion. The page supplies a calm frame for an animated character whose anticipation, mishaps and recovery supply the humor. Preserve the approved artwork and choreography when extending this system.

**Key Characteristics:**

- Original outlined raster character with neon color baked into its assets.
- Warm neutral stages and a dark simulated camera frame.
- Condensed display type paired with plain functional body text.
- Three authored arrivals and departures sharing one five-second performance.
- One inspection clock for pictures, bounded effects and sound.

## Colors

The shell uses warm paper and muted green-black; concentrated lime, orange and magenta belong to the character and its effects.

### Primary

- **Vermilion** marks the second headline line, selected sequence title, sound-on state, timeline, action hover and focus outline.
- **Phosphor** supplies the face's bright family and the portal rim, dash speed marks and portal particles; **Flash** supplies sparks and lighter portal details.

### Secondary

- **Orange**, **Lemon** and **Hot** layer the rocket flame. Orange also anchors the baked sneaker family.
- **Magenta** supplies rocket-launch particles and the photograph's bright family. The photograph's violet and blue are baked graded raster colors, rather than additional flat effect tokens.
- **Active Green** on **Active Paper** distinguishes the current sequence badge.

### Neutral

- **Paper**, **Ink**, **Quiet** and **Rule** organize the review page; **Preview** separates the character stage without a card border.
- **Button Cream** on Ink identifies the shutter and finished-stage replay actions; **Button Hover** lightens their fill on hover.
- **Camera Case**, **LCD Dark** and **LCD Cream** supply the simulated camera and photographic readouts.
- **Glass**, **Portal Depth** and **Portal Rim** give the portal an outlined hollow center. **Ivory**, **Sprite Ink** and **Sprite Shadow** support dust, effect outlines and the grounding ellipse.

**The Baked Color Rule.** Grade the raster color channels while preserving source registration and alpha; keep original masters. Reuse the shared neon palette for geometric effects. Do not add glow or runtime image filtering.

## Typography

**Display Font:** the locally loaded `Barlow` face, with Arial and sans-serif fallbacks. The product brief describes its condensed display character; the actual CSS family is `Barlow`.

**Body Font:** Arial, with a sans-serif fallback.

**Character:** Tall, compact headlines give the review page its editorial emphasis. Plain body lettering keeps the explanations and playback controls utilitarian.

### Hierarchy

- **Display:** the frontmatter's desktop heading, rising to (88px) from (1450px), falling to (62px) at (1100px), then resetting to (68px) at (790px). It wraps naturally on narrow screens.
- **Title:** sequence headings use the title role; at (1100px) they become (23px), and stacked study titles become (28px) at (790px). The concluding section title is (29px).
- **Body:** introductory copy uses the body role, with (16px) at the wide breakpoint. Its desktop width is (350px), becoming (380px) on wide screens and up to (50ch) when stacked.
- **Caption:** study descriptions use the caption role, constrained to (35ch) on desktop and released on mobile.
- **Action:** shutter and stage replay labels use the action size. Inspection notes, personality captions, elapsed time, sound, secondary controls, study metadata and per-study Play labels use the inspection role. Cues and footer text use the supporting role. Miniature camera readouts reproduce the hardware display and do not set the size of page controls.

**The Two Voices Rule.** Keep Barlow for major headings and Arial for explanations, measurements and controls.

## Layout

The centered page has a maximum width of (1500px) with the frontmatter's page inset. Navigation is (92px) high. The desktop introduction places headline and explanatory copy side by side. A ruled transport row precedes a flexible secondary control row, then three equal study columns with the shared column gap. Each study presents its title, large character stage, camera preview, sound metadata, description and Play action in that order.

At (1450px), the column gap grows to (40px). At (1100px), page insets become (28px), column gaps become (22px), and redundant Play-row cues hide. At (790px), the header stacks, studies become one column capped at (500px), cues return and transport controls wrap with the range and time on a later row. Secondary source and decision-detail text hide; footer content stacks.

The camera uses a (3:2) LCD. Its internal coordinate plane is (720 × 480), scaled to the available width. The mascot overlay sits at the lower right in a (240 × 176) region, inset (16px) from the right and (45px) from the bottom. Large review stages use a wider SVG viewBox to reveal the action while keeping native sprite dimensions separate.

## Elevation & Depth

The page is flat, separated by tonal fields and thin rules. The camera alone carries a diffuse shadow (`0 8px 16px #202a2417`) to read as a physical frame. LCD readouts carry a small black text shadow over photography. A low-opacity ellipse grounds the mascot and fades with its height and lateral travel. Portal depth comes from nested dark fills and a front rim that overlaps the character.

**The Material Depth Rule.** Keep depth tied to the camera, photograph readability and the character's physical action; preserve the neutral page's flat separation.

## Shapes

Large stages and camera frames share softly rounded surface corners. Smaller controls use tighter radii; the LCD has compact corners. Thin rules, small circular sequence indices and status dots support inspection without surrounding every study with a card. The mascot keeps its authored irregular ink silhouette. Effects use simple ellipses, rectangular pixels, line marks and layered flame paths, with front/back portal occlusion.

## Components

### Buttons

The shutter is a compact filled action with an outlined SVG camera icon and cream text. Its dark fill lightens on hover. Finished stages expose a centered replay button in the same palette. Per-study Play actions span their column, use a top rule and outlined SVG play icon, and turn vermilion when selected or hovered. Secondary entrance/exit replay controls are text actions with an underline-like bottom rule and authored SVG reset/arrow icons. Play/pause occupies (44 × 44px); sound and secondary transition replay controls have a minimum height of (44px). Global keyboard focus uses a vermilion outline (3px) offset by (5px). No animated hover lift is present.

### Timeline and sound

The native range uses the vermilion accent and tabular elapsed-time digits. Scrubbing pauses motion and sound. The sound control pairs an outlined SVG speaker with a text state and `aria-pressed`; browser audio failure produces a status message. Sound starts from user action. Pocket Lab notes and transition SFX share the playback clock, with application master gain at unity and layered effects staged through a limiter.

### Active sequence badge

The noninteractive green-on-pale-green badge reinforces the selected heading color. Its small rounded rectangle and explicit ACTIVE text communicate state rather than an action.

### Study and camera previews

Stages center the raster character and clip outer travel. Camera frames show the same selected playhead on a dimmed photograph; inactive studies retain a fixed inspection pose. The active study also changes title color and shows a text badge, so selection has more than one visual cue. The stage clears when the complete sequence finishes and offers replay.

### Terminal performance

The shared cycle is (1400ms) entrance, (5000ms) acting and (1200ms) exit. Disk Dash, Pixel Portal and Rocket Delivery are retained in shuffled sets of three without immediate repeats; manual Play selects one for inspection. Twelve cached (128 × 128) poses and (30fps) sampled transforms keep the native treatment bounded. High-resolution raster counterparts serve the review stage.

**The Shared Clock Rule.** Sample paused choreography from the common playhead. Pause, seek, a fresh shot and page hiding stop owned sound; no autonomous tween may outlive the inspection state. Preserve anticipation, travel-facing turns, squash, rebound and follow-through. Reduced motion initially presents the fixed finished pose with an explicit full-motion preview control, and CSS transitions are disabled under that preference.

## Do's and Don'ts

### Do:

- **Do** preserve the original CRT silhouette, alpha, registration and dark ink while grading its accent colors.
- **Do** use the shared palette for bounded geometric effects and baked colors for raster art.
- **Do** keep a large inspection stage alongside the native-size camera treatment.
- **Do** preserve all three transitions, the full five-second routine and the shared clock.
- **Do** expose pause, scrub, specific-sequence Play, transition replay and sound state.

### Don't:

- **Don't** add glow passes or runtime filters to achieve the neon treatment.
- **Don't** replace authored entrance/exit poses with a slide of the idle character.
- **Don't** enlarge the native sprite budget to match the high-resolution review stage.
- **Don't** treat decorative camera readouts or existing microtype as a minimum legibility standard for new interactive controls.
- **Don't** treat browser previews as proof of physical-camera integration.
