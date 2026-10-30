# V5.0.1: Hermes 0.22.x seams and durable PM dependencies

This patch addresses the missing completion/approval anchors in #428 and HFC disappearing after PM environment replacement in #431. Installable availability is determined by the GitHub Release tag and assets.

## Changes

- For the pinned Hermes revisions `297552a9d646119871391d202509822cd86330df` and `7bda2a3368024f7ae1c70cef16583e7c2c891674`, verify imports, inheritance and absence of MRO shadowing before patching the actual completion owner in `GatewayTurnPersistenceMixin`. Timing remains in the original handler; unknown source contracts remain rejected.
- Support `_render_approval_sync` after the native generation check. Resolve through the original Hermes request handle exactly once, preserve authority/viewer ordering, and reject resolution if the generation changes during the wait. Settled approvals are not revived.
- Extend an existing V4 manifest only after verifying its backups and ownership, with explicit `--accept-hermes-upgrade`. Restore returns the updated Hermes sources to their original bytes.
- PM-managed installations register a dependency-only member through the official `hermes_cli.plugins_admission.admit_plugin_set_change` API. Cache the exact ordinary wheel and declare a local `tool.uv.sources` path so future workspaces install the same bytes. Registration is required even if that version already imports. Re-select the committed venv afterward and verify installation provenance and package resources.
- Hold the installation lock through registration, finish, rollback and removal. Roll back only changes owned by this installation, preserve existing selections/disabled values and other configuration, and retain diagnostic sources when commit status is uncertain. Restore keeps the dependency; uninstall removes HFC's unchanged, newly owned registration after restoring hooks.

## Compatibility and upgrade boundaries

Detection for the two reported revisions is `partial`: required completion/approval seams are verified, while the extracted optional progress status callback and the new provider/model capture point in `_run_sync_scoped` are outside this patch. Those paths retain native or unknown-value behavior. This is not full status/metrics coverage or a claim of support for arbitrary latest Hermes main. Other pinned-source matrix coverage remains unchanged.

Use the official installation flow to update to `v5.0.1`, retaining your config, env file, Hermes HOME and service ownership. Do not edit installed Hermes sources or PM facts/lock manually. Explicitly disabled members, unknown directory ownership, user edits, dependency conflicts and uninspectable file state refuse overwrite. See the [maintenance guide](wiki/maintenance-guide.md#hermes-022x-与-pm-依赖登记) and [upgrade guide](upgrade-v4-to-v5.en.md). Python support, card defaults and native interaction authority remain unchanged.

## Verification boundaries

Coverage includes pinned-source install/repeat/doctor/integrity, old-layout migration and exact restore; original Hermes approval queue/controls with duplicate, late and generation-change cases; and independent ordinary-wheel child imports across real upstream PM engine generations. Final wheel package resources are compared byte-for-byte with source; portable publication has fault-injection coverage. Full platform CI, the exact merge/tag, assets/checksums and public-tag installation follow the [release playbook](wiki/release-playbook.md).

PM integration uses a private HOME and minimal project with the existing uv/Python toolchain injected. It does not execute the full Hermes dependency closure or PM worker transport. This patch adds no production updater, real Gateway/model/Feishu or Windows-host acceptance. Source compatibility and automation do not establish those results. Card layout is unchanged; no new client visual acceptance is claimed.

## Credits

Thanks to [lanx214](https://github.com/lanx214) for [#428](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/428) and [#431](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/431), and [za8209](https://github.com/za8209) for macOS reproduction logs and source analysis in #428. Thanks to [Lite-G](https://github.com/Lite-G) for the independent compatibility analysis and proposal in [PR #432](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/432); that PR's code is not included in this release. These credits distinguish issue evidence and independent proposals from this release's code authorship. All earlier README, release-note and Git-history credits and original commit authors remain intact.
