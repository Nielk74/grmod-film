# WP12 — repair the existing development bootstrap

**Relevant source:** `ui/src/engine.ts`, its module-level Worker constructor. Actual Vite 5.4.21 development startup repeatedly failed with `worker-import-meta-url: Vite is unable to parse the worker options as the value is not static`, pointing to the existing `type: import.meta.env.DEV ? 'module' : 'classic'` option. The failure was observed before edits during the completed desktop browser work; production builds and the production browser pass separately. This is a concrete existing tooling defect, not another firmware/image candidate.

The user authorizes autonomous project exploration and fixes. This new bounded scope supersedes the prior desktop round's exclusion of the firmware client for this single constructor-only change. Preserve all worker protocol, message routing, heartbeat, Engine calls, native/firmware sources, colour assets and sealed packet data.

## Exact manifest, declared before source edits

| File | Change |
|---|---|
| `ui/src/engine.ts` | Put the environment branch outside the Worker options, with separately statically analyzable module/development and classic/production constructors; preserve URL, transport and every other statement |

Root owns the change and this document. Evidence/scripts remain ignored under `research/gr3-210/wp12-dev-bootstrap`. No test-source, configuration, dependency, native/generated, schema or other production path changes are required. The preceding desktop sources are preserved in the exact thirteen-file overlay; the unchanged pre-fix client is also in the parent round-one snapshot.

## Verification and kill

The observed failing development transform is the red control. Start the real Vite dev server after the change and verify an actual isolated Edge page boot, supported GR III 2.10 open and worker activity without the overlay/page error. Run core/UI typechecks and production build, inspect its classic Worker constructor, repeat the applicable core suite once on settled sources, and confirm source diff is confined to the constructor. No implementation-mirroring unit test is added for this small build-tool expression change.

**Kill:** revert this one source change if development cannot parse the static calls, production ceases to use a classic worker, transport/heartbeat changes, or the existing GR III workflow fails. Do not turn it into a worker/client refactor or dependency update. No release, push, commit, device operation or camera claim follows this fix.

## Local browser environment

The root dependency directory is an ignored junction into the primary checkout. Vite development opens the firmware and receives heartbeat replies after the constructor fix, but rejects the junction-resolved font URLs outside this checkout. For the isolated browser gate only, an ignored `vite.fixture.config.mts` spreads the unchanged project config and allows that already-used dependency directory. It changes no production config or dependency and is not part of the application fix. The initial browser attempt is preserved as `dev-browser-junction-attempt.json`; its overlay is an environment/font-serving failure, with no page errors and successful firmware/heartbeat. The final gate must still have no error overlay.

## Verified outcome — closed

The one-file fix passes actual Edge development/module and production/classic startup, official GR III 2.10 opening and repeated heartbeat without page errors or overlay. Core/UI typechecks, production build, independent constructor review and the full applicable suite pass: **263 passed, 175 skipped** in 56.77 seconds. The previous thirteen desktop source pins and thirteen sealed packet pins remain unchanged. The production entry/worker keep their content-hash filenames and exact earlier constructor snippets. No kill occurred; retain the narrow fix and stop this round. Evidence and the one-page report are under `research/gr3-210/wp12-dev-bootstrap`; `engine.verified.ts` preserves the additional source overlay. Both verification servers were stopped.
