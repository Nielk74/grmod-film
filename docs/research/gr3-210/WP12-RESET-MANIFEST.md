# WP12 — optional GR III 2.10 library reset guide

Date: 2026-11-09. Base `db76c9b42f85d657a760d07af97735854f253c57`. Two existing-source audits find a concrete discoverability gap: factory-return confirmation has partial reset copy, but modified-library exports and the Guides menu do not expose the complete documented sequence. See `research/gr3-210/wp12-reset-guidance-01` and `wp12-reset-guidance-source-review`. The latter verifies the written instructions only; camera behavior and recovery efficacy remain untested. The brief's November 5 attribution is qualified, not a confirmed diagnosis.

## Exact three-file manifest — before edits

| Owner | File | Change |
|---|---|---|
| Guidance implementer | `ui/src/app.tsx` | Add one optional guide with contextual export access and a Guides-menu entry, scoped to the selected supported GR III/GR III HDF 2.10 file; private UI state only |
| Guidance implementer | `ui/src/i18n.ts` | English/Chinese labels and complete source-grounded steps/compatibility/return/identity copy |
| Guidance implementer | `ui/src/styles.css` | Locally scoped nonmodal reading panel with bounded scrolling and minimum-window behavior |
| Root | This manifest, `PLAN.md`, `PRODUCT.md`, `docs/GR3_EXPLORATION_REPORT.md` | Plan and verified outcome |

Evidence and the three-file before/final overlays belong only under ignored `research/gr3-210/wp12-reset-guidance-implementation/**`. No store/engine/export/receipt/schema, test-source, core/native/generated, source colour, dependency/config, packet/card or other production path may change. This is a small reversible information/UI feature; no unit tests mirroring static copy are added. Meaningful behavior is verified in the actual browser with existing checks.

## Concrete behavior and copy

- Reuse the existing Guides (?) menu and add a contextual, nonblocking access point beside supported export. Both open the same dismissible **nonmodal** reading region. The existing narrow, noninteractive `Hint` is unsuitable for the complete sequence.
- Preserve normal export/write actions and confirmations. No acknowledgement, automatic appearance, automatic setting reset, new firmware download, filesystem action or installation capability is introduced.
- Keep keyboard access, an accessible region name, a labelled close control, Escape/outside dismissal and sensible focus restoration. Other app controls remain usable. Hide/close it when the selected model/open file leaves the supported scope. Both wide and supported 980 × 640 layouts must fit with all text reachable by scrolling.
- Scope explicitly to GR III / GR III HDF **2.10**, with no IIIx/IV inference or 2.20 path. A selected model/open firmware is UI applicability, not proof of what is installed.
- Preserve the exact five ordered existing steps: 3:2; factory Image Control/Standard with Clarity 0; timestamp Off and End Screen Picture Original with saved-mode precautions; camera reset; only then the intended verified file. Include U1/U2/U3, repeat the full sequence before returning, and manual restoration of ordinary settings.
- Retain the original historical 12+/13+ compatibility conditions, no-film parameter carry-over and T6d record caveat without guessing the user's installed historical stage. These may be a separate readable compatibility section. Do not label historical step numbers as firmware versions.
- The source Chinese path is `设置 › 重设 › 恢复默认设置`; the card's English `Settings → Reset → Restore Default Settings` is explicitly a translation, not an observed camera label. Do not invent gestures or silently resolve the existing wording variation by claiming native verification.
- Do not bake private local research paths, test binaries or their hashes into the product guide as universal installation targets. Explain using the intended file and its own test card/verified return recipe, repeating all reset steps before return. Only a known installed file/hash is a declared baseline; otherwise identity is unknown. Host receipts, EXIF Software, filename or save order do not establish installed identity.
- Written guidance is not a new recovery procedure, a safety guarantee or camera-test approval. Avoid claiming the earlier persisted-settings incident has a confirmed cause. Preserve the immutable test card and all finished source epochs.

## Verification and kill

The source audits establish the missing affordance as the pre-change control. Capture the old production UI's absence before testing the new panel. Root/independent reviewer check copy against both pinned sources, including both languages and historical qualifiers. Run core/UI typechecks, production build, existing tests and one settled full suite. Browser checks exercise both discovery points, keyboard/open/close/Escape/outside behavior, focus, complete readable/scrolled instructions, supported minimum window, scope exit and an unsupported model. Browser host APIs are mocked; no camera/card/real file operation is performed.

**Kill/revert:** an instruction requires a new camera gesture or ungrounded recovery claim; exact steps/qualifiers cannot fit accessibly; the guide becomes an export barrier or triggers an operation; unsupported scope is advertised; or build/browser checks fail after the bounded implementation. Do not turn this into an installer, setting reset service, hardware probe or new camera test. No release, publication, device write or flash follows.

## Verified result

The three declared source paths pass the final 281/175 suite with real receipt replay, core/UI typechecks, production build and whitespace check. Actual Edge confirms both entry points, English/Chinese minimum-window reading, Close/Escape/outside focus behavior, source/model exit and unsupported IV absence, with zero build/write/operation calls. Review's one P2 language-tag defect is resolved within app/i18n: the panel follows the UI dictionary rather than the independently selected camera language. Both independent reviews match the corrected source pins. The preserved overlay `research/gr3-210/wp12-reset-guidance-implementation/source-final.json` hashes to `05f458ad8171bf41e67c9c0e338f7df303cab7b1eff83a8bae56daa613a67fdf`; all 168 composed code/config pins and thirteen sealed packet hashes match. Both workers are unchanged. Browser server stopped; no camera validation or recovery guarantee follows. Detailed gate record: `root-verification.json` in that evidence directory.
