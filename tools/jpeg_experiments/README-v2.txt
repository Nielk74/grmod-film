Visible JPEG experiments v2 — 31 October 2026

Open C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-v2-2026-10-31/index.html.
The local server, when running, is http://127.0.0.1:8747/.
Before / After buttons and A / B / space support whole-photo flicking.

The v2 colour baseline is the existing fitted colour transform (neutral user
controls, grain/clarity fixed), applied to R0000022/23: documented Standard
JPEGs in ui/src/assets/samples/CREDITS.md. It is a coefficient-based reference,
not a physical ISP reproduction. The two photos show one scene, not broad
photographic or skin validation. Classic Chrome/Neg are stronger yardsticks
than Astia on this scene. The stronger targets are authored inside each film,
then passed to the real Engine conversion against official GR III 2.10.

Main PNGs have an 1800px long side. Final main metrics read those PNGs back
and evaluate them at 900px. Fixed colour masks use the before film, never the
after or top-changing pixels. Main colour variants pass mean targeted dE00>=3
in the exported images. This is a visibility gate, not a quality score.
Sweeps/target diagnostics retain their pre-export floating display metrics.
Fit errors, authored-effect size and exported-effect size are different values.

RAW before files are the paired camera JPEGs. RAW DefaultCrop and orientation
are verified against LibRaw metadata before resizing; the roof frame has a
substantial camera crop. Record exposure=1, recorded camera WB and the common
decode explicitly. The designed RAW curves are not existing GR Mod film profiles.
The ordinary RAW S-curve is diagnostic, not the main before. RAW-versus-camera
differences include colour interpretation, demosaicing and lens geometry;
they are not colour-accuracy or highlight-detail recovery measurements.

Recommended review: 01 yardstick, 03 hue, 04 density, 10 jointly fitted colour,
then the conditional spatial/RAW ideas. Read findings.txt and per-folder
judgement.txt. Strength extremes are retained, including rejected outcomes.

Reproduce in PowerShell from the repository root (output is the fixed v2 path):

& scratch/jpeg-experiments-env/Scripts/python.exe -m pip install -r tools/jpeg_experiments/requirements-v2.txt
& node_modules/.bin/vite-node.cmd tools/jpeg_experiments/film_pipeline_v2.ts -- research/camera-ui/downloads/gr3_v210/fwdc239b.bin C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-v2-2026-10-31/models
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/v2_compare.py
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/v2_curate.py
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/v2_verify.py
& scratch/jpeg-experiments-env/Scripts/python.exe -m pytest tools/jpeg_experiments -q -p no:faulthandler
npm test

Native research, using the existing research environment with its native harness:

& research/camera-ui/venv/Scripts/python.exe tools/jpeg_experiments/gr3_multi_axis_probe.py --output C:/path/to/fresh-hue-evidence
& research/camera-ui/venv/Scripts/python.exe tools/jpeg_experiments/native_tone_probe_v2.py --rtos research/camera-ui/evidence/gr3x-160-rtos.bin research/camera-ui/hardware-prep/gr3-210-rtos.bin --base research/camera-ui/evidence/adj-base-manifest.json --out-dir C:/path/to/fresh-tone-evidence

The native probes write evidence only. Per-film multi-axis selection/packing is
verified, but hue-sector ISP semantics remain unverified. Copying GR IV blocks
would be unjustified. The tone probe tests Image Control sliders, not separate
automatic D-Range correction. Native Shading already supports film defaults;
its radial shape/EV mapping to this vignette is uncalibrated. HDR Tone and
Shadow Correction may be related to local range, without a measured match.

Windows runtime note: Python faulthandler prints a non-terminating Unicorn
access-violation diagnostic at mem_map in the tested Python3.12/Unicorn2.1.4
configuration. The same message reproduces in an isolated memory-map/read/write
program with no firmware, after which execution and tests continue. Plain
unittest and pytest with faulthandler disabled complete without that diagnostic.
This is not described as a clean faulthandler run or a universal runtime guarantee.
The optional missing-Matplotlib warning concerns colour-science plotting API;
the numerical colour-difference functions do not require plotting libraries.

The first output folder is preserved. No original photo or production/core
source was edited, no firmware was installed, and no release was published.
