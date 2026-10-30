# V4.0.12

V4.0.12 addresses Issues #133 and #136: Hermes context compaction no longer creates a silent card gap, five card text roles can be sized per PC/mobile client, and a credential-free sidecar no longer disguises Noop delivery as healthy/successful.

## Visible context compaction

- The patcher converts only Hermes' exact `_status_callback_sync` `Compacting context` marker into a `context-compaction` notice. It does not infer compaction from generic compression text, a silent watchdog, or fabricated percentages.
- An existing primary card shows “正在压缩上下文” in its Header. If no card exists, the sidecar creates exactly one primary card while preserving DM/topic reply anchors.
- Later answer/tool/terminal events clear the compaction phase and continue updating the same card. Doctor/capability diagnostics explicitly report whether `status_callback` is available.
- Hermes versions without a compatible callback remain fail-open without disrupting other card paths.

## Configurable text sizes

- `card.text_sizes` supports five roles: `body`, `reasoning`, `tool`, `notice`, and `footer`.
- Each role accepts one Feishu CardKit size or a `default` / `pc` / `mobile` mapping. Base/profile/bot layers use a controlled deep merge only for this field.
- The closed schema accepts only known roles, device fields, and CardKit sizes. Errors include the exact config path without dumping config or credentials.
- With no configuration, the existing default Card JSON structure is preserved. Physical card width/height remains controlled by the Feishu/Lark client and is not promised by this release.

```yaml
card:
  text_sizes:
    body: normal
    footer:
      default: x-small
      pc: x-small
      mobile: notation
```

## Selected env and observable Noop delivery

- The env file selected by `setup` / `start --env-file ...` now supplies Feishu credentials to both the runner and operations diagnostics. Precedence is YAML < config-sibling `.env` < selected env file < process environment.
- The runtime does not unconditionally read a global `~/.hermes/.env`, avoiding accidental cross-profile, container, or custom-config credentials. Installer-owned `HFC_ENV_KEYS` remain secret-free.
- Missing credentials produce a clear warning without paths or secrets. `/health` reports `status: degraded`, `noop_mode: true`, and `delivery.mode: noop`.
- Noop sends return `not_sent`, increment `feishu_noop_attempts` and `feishu_send_failures`, never fabricate a message ID, and never increment `feishu_send_successes`.
- Process management treats a degraded sidecar as running but unable to deliver, so `start/status/stop` can still manage and repair it.

## Verification boundaries

- Automation covers compaction patch/install, status classification, session/render/server lifecycle, topic/sequence races, capability/doctor diagnostics, plus text-size schema, merge, role rendering, and PC/mobile aliases.
- The final full suite reported `1460 passed, 4 skipped`, and `git diff --check` passed.
- `uv build` produced both sdist and wheel. A clean Python 3.12 environment imported `hermes_feishu_card==4.0.12` with matching distribution-version and console-entry-point metadata.
- A real selected-env subprocess starts as `healthy/live`; a credential-free subprocess starts as `degraded/noop`, returns `not_sent`, and keeps successes at zero.
- The candidate runtime was installed into a real Hermes instance through official setup/patcher paths. Doctor confirmed the `status_callback` capability and consistent install state; the text-size demonstration card completed create + update.
- Manual `/compress` does not traverse `_status_callback_sync` and is not accepted as automatic-compaction callback evidence. By release decision, the automatic long-session compaction smoke was not run. This release does not claim final desktop/mobile visual acceptance or reporter-side Linux/systemd revalidation.

## Release assets

- `hermes-feishu-card-v4.0.12-macos.tar.gz`
- `hermes-feishu-card-v4.0.12-linux.tar.gz`
- `hermes-feishu-card-v4.0.12-windows.zip`
- `hermes-feishu-card-v4.0.12-checksums.txt`

Post-release verification: annotated tag `v4.0.12` points to merge commit `00a48a7`, and release-assets workflow `29632908140` succeeded. After downloading all four public assets, SHA-256 verification passed for the Linux, macOS, and Windows packages. An isolated Python 3.12 environment installed the public tag, imported `4.0.12` from `site-packages`, and passed the CLI smoke. Issues #133 and #136 were closed with the remaining verification boundaries documented.

## Credits

- Thanks to @tianxia3111 for Issue #133's production compaction gap and mobile-readability request.
- Thanks to @Jasonsun77 for reinforcing the configurable-font request.
- Thanks to @nasvip for Issue #136's complete Linux/systemd credential chain, health/metrics evidence, and root-cause analysis.
