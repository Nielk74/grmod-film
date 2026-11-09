# WP10 — autofocus frozen pending a named failure and baseline

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim:** the exploration mapped AF controls and acquisition boundaries but demonstrated no improvement in speed or accuracy.

**Evidence class:** source, emulated functions and photo metadata. Delivered requests reach actual Caf preparation; hardware property/statistics responses remain outside the verified path. Real AFInfo records do not provide acquisition timing or error ground truth.

**Decision:** freeze all AF tracing, predictor/threshold/lens tuning and orientation-point recall. Keep the reusable address/evidence map. The user requested exploration of AF, but has not named a failure that justifies further tuning; apply the brief's kill criterion without another question.

**Next step:** only reopen after a specific problem and a stock baseline exist. A future baseline uses fixed targets, controlled starting focus, phone high-frame-rate recording and sharpness of captured results. It does not require modified firmware.

**Kill criterion:** no named failure, or acceptable stock behavior: keep AF frozen.

**Limit:** no timing unit, confidence threshold or synthetic wave experiment establishes a physical improvement.

## Preserved conclusions

- Hidden scan-range static tracing is closed. If justified later, one controlled hardware dialog test replaces further tracing.
- Temporary Select AF is already a stock function; the redundant candidate is dropped.
- Metadata AF-area coordinates and crop clamping are reusable evidence, not proof of focus accuracy.
- Command packets retain only the low clock word and can stamp zero on failed reads. They are not acquisition measurements.
- Orientation recall must not treat record-pointer identity as owner generation or blindly invoke touch-AF's state-changing path. This is retained as a caution, not an active feature task.

Any passive trace build is later work and must first have a baseline, a named result path and bounded per-photo/RAM storage. No new file-I/O path or AF tune belongs in T-texture or T-colour.
