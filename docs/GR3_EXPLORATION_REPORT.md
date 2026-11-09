# Ricoh GR III 2.10 — decisions and next actions

Updated 2026-11-09. [Active brief](research/gr3-210/BRIEF.md). Branch `codex/gr3-crop-texture`; integrated base `db76c9b42f85d657a760d07af97735854f253c57`. Source and the initial 25 documents are saved in local commit `a0bdde5`; Portra colour is unchanged.

The earlier conclusion that no further host direction survives is withdrawn. Several directions await a preference only the user can supply. This remediation produced one MTF proxy and a haze diagnosis, corrected the card, and saves the work. Stop after its final checks and local commit; no automatic new round.

## Top five actions

1. Judge the seven linked comparisons in [USER-DECISIONS.md](../research/gr3-210/USER-DECISIONS.md), recording a preferred variant or no useful difference for each. WP5/WP6 remain pending.
2. Answer the focus choice there: low-light hunting, macro, wrong target, speed, or none. No AF work starts in this round.
3. Review the revised [common camera card](../research/gr3-210/test-session/ready/TEST-CARD.md), including Return's missing shot animation; if undertaking the session, follow baseline → reset → T-texture → reset → T-colour → reset → return. Only the operator flashes, staying on 2.10.
4. Return the card's 28/35/50 mm and true XS comparisons, post-view/playback observations, A/B/A developments and conditional A/B captures, plus matched Standard/film/WB outputs and the four-capture grain alternative. Analyze only the tested routes.
5. Decide sensor/output adoption and approved-Gold licence treatment before public shipping; approve any push separately. Sensor adoption remains blocked by crop/resize ambiguity and XS's 6000-frame MTF.

## Decisions and work queue

| Package | Current decision | Next step / kill criterion |
|---|---|---|
| [WP1 base](research/gr3-210/BASELINE.md) | Source committed; packet/checkpoint copied and rehashed outside the checkout | Preserve local commits/backups; reject a mismatched restore. No push authorized |
| [WP2 crop texture](research/gr3-210/CROP_TEXTURE.md) | Fresh source rebuild exactly matches sealed T-texture; camera untested | Operator crop/XS tests, then user choice; unsafe descriptors/parity failure reject candidate |
| [WP3 hue](research/gr3-210/COLOR_AXES.md) | Host probe build ready; RAW development and capture may be different routes | A/B/A first; if equal, one conditional A/B capture pair. Negative result closes only its tested route |
| [WP4 exposure](research/gr3-210/EXPOSURE.md) | Approved Gold preserved; CineStill and optional Portra sheets await preference | User chooses; no winner means no adoption, no default Portra change |
| [WP5 MTF](research/gr3-210/MTF.md) | One Vision3 ordering proxy made; user preference pending | Judge at 100%; user sees no useful difference closes this candidate. Gold sources still lack curves; calibrated fitter remains no-go |
| [WP6 grain](research/gr3-210/GRAIN.md) | Two sheets made, neither judged by user; kill not met | User selects baseline/variant/no difference. No automatic third round |
| [WP7 WB](research/gr3-210/WHITE_BALANCE.md) | Same-DNG comparisons prepared | User prefers AWB: close fixed-policy work |
| [WP8 model](research/gr3-210/CAMERA_VALIDATION.md) | Existing analyzer/intake ready; no completed camera return contract | Analyze supported matched returns; dominant residual stops finer fitting |
| [WP9 JPEG](research/gr3-210/CAMERA_VALIDATION.md) | Custom grain and halation RAW controls not established independently | Card's four grain captures with halo Off; eight-way RAW matrix still deferred. No useful tradeoff stops encoder tracing |
| [WP10 AF](research/gr3-210/FOCUS_FROZEN.md) | Pending required user choice, previously skipped | No AF work now; only an actual answer/baseline can satisfy the brief's kill |
| [WP11 Snap / WP12 product](research/gr3-210/PRODUCT.md) | Existing host tools saved; scoped native contract no-go results retained | Use tools within evidence limits; no new features/native tracing this round |

## Evidence and limits

- In this programme, “independent review” means separate subagents checking the same local evidence, not outside reviewers. Independent codec checks additionally use a separate implementation.
- The historical 170-file raw source checkpoint contains **47 real source/config changes (33 modified + 14 new) and 123 EOL-only differences**, plus a separate dated 25-document snapshot. Commit `a0bdde5` saves the 47 changes and 25 documents with Git-normalized source line endings. [Checkpoint](../research/gr3-210/source-checkpoint-01/REPORT.md); [backup verification](../research/gr3-210/review-remediation-01/backup-verification.json). The backup precedes the card revision.
- Refreshed origin branches do not contain `db76c9b`. A push would upload it and subsequent local commits, creating/updating `codex/gr3-crop-texture`; it would not merge main. Explicit approval is required before any push.
- [Fresh rebuild](../research/gr3-210/review-remediation-01/rebuild-verification.json): T-texture SHA-256 `631974813579e055a65f80c1558133acd7f27259edf2b4dcfb9dc052c2f21768`. All three packet firmware hashes remain unchanged. Only TEST-CARD and its SESSION-MANIFEST/SHA256SUMS bindings changed; [exact old/new hashes](../research/gr3-210/review-remediation-01/card-revision.json).
- The 720/160 px preview exclusions come from source/fixtures. `wp2-audit/preview-sizes.json` has **27 null tags**, not observed live descriptor widths. The 27 real JPEGs' focal-length metadata identifies 25 crops; dimensions alone do not identify future crop versus resize jobs.
- [Haze diagnosis](../research/gr3-210/review-remediation-01/haze/REPORT.md): exact approved-Gold GUI reproduction; Off/1/Medium for three colours and legacy proxy all checked. Provisionally too strong for these bright facade highlights; no demonstrated new preview integration defect, no strength/code change, no documented camera halation positive control established.
- [One MTF proxy](../research/gr3-210/review-remediation-01/mtf-proxy/REPORT.md): **Vision3 ordering proxy, not measured CineStill**. Equal neutral luma per band, literal source DQT/4:2:2, fixed authored CineStill colour, grain/halo Off; native Standard daylight/night 100% panels. No fitter, new native gains or winner.
- [Crop-export browser gate](../research/gr3-210/wp12-comparison-crop-browser/acceptance.json): 26 steps and five PNG decode checks used intercepted host APIs, **realApiWrites = 0**. No save passed through the real Go shell. Other host gates do not establish camera operation.
- Final remediation verification: **329 passed / 175 skipped** with `GRMOD_GR3_FIRMWARE=<official GR III 2.10>` and `GRMOD_RECEIPT_REPLAY=1`, `GRMOD_RECEIPT_EVIDENCE` unset; plain run **304 passed / 200 skipped**. The 175 skips include GR IIIx and GR IV fixture paths. Core/UI typechecks and UI build pass. Packet integrity and all 21 staged paths pass; staged packet text retains exact raw bytes. Logs and `final-verification.json` are under `review-remediation-01`; historical topic/manifests retain their stage counts.
- [Plan](research/gr3-210/PLAN.md), [reference identities](research/gr3-210/BASELINE.md), and `tools/gr3x/symbols-gr3-210.json` preserve reusable decisions. Historical ignored evidence stays local; no new large manifest is required.

Nothing new here has passed a physical camera test. No push, release, device/SD write or flash occurred. Public shipping/licence treatment remains open. Future work requires the user's next instruction after this round stops.
