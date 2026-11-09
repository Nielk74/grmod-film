# WP7 — white balance as a film choice

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim:** the ten-byte film recipe does not carry WB; fixed WB may preserve a preferred illuminant character that AWB changes.

**Evidence class:** source for recipe scope; aesthetic hypothesis for the rendering.

**Decision:** test the visible choice with existing in-camera RAW development before tracing a new per-film WB policy. This needs no test firmware.

**Next step:** the common test card uses mixed-light DNGs for CineStill at AWB, 3200 K and 4300 K; Gold and Portra compare AWB against fixed daylight. Preserve original DNGs and return the new JPEGs with named settings.

**Kill criterion:** AWB is preferred: stop the per-film WB-policy direction.

**Limit:** fixed WB is not automatically a more accurate film response.

Only after a fixed policy wins should film selection apply it and restore the prior WB on exit. Illuminant-conditioned fitting remains later work and is not required to run this first comparison.
