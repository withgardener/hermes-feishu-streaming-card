# V4.0.15

V4.0.15 fixes Issue #141 and adds user-side protection for Hermes upgrades that replace the injected Gateway hook.

## Tool events and loading state

- Tool events use a compact two-level timeline: the first line contains semantic status, tool name, and duration; arguments, results, and failure details stay on a smaller second line without a Markdown blockquote background.
- Before the first model or tool event, the same card displays an animated `正在加载上下文…` state; running tools reuse the spinner.
- Animation advances through the existing serialized `FlushController` PATCH path every 0.8 seconds for at most about 12 seconds. Visible body text, a terminal tool update, or a terminal message stops it without changing the message id, topic, or reply anchor.
- Success, running, failure, cancellation, and waiting retain deterministic semantic states; terminal drain and native-message suppression boundaries are unchanged.

## Hermes upgrade protection

- `status` / `start` resolve `HERMES_DIR` from `--hermes-dir`, the selected env file, the config-adjacent `.env`, or process environment and inspect hook state read-only.
- A verified Hermes source replacement reports `hook.status: upgrade_repair_required`. `start` refuses before launching the sidecar and prints the explicit `install --accept-hermes-upgrade --yes` and `hermes gateway start` commands.
- User edits, corruption, unsupported source, or incomplete evidence report only `manual_review_required`; the CLI does not offer an upgrade-acceptance bypass for these states.
- When installation actually changes Gateway or cron source, it prints `gateway.restart_required: hermes gateway start`.

## Validation

- Real Feishu validation with the configured Hermes model `deepseek-v4-flash` covered the initial loading spinner, running-tool transition, and one-card terminal result with no delivery or update failures.
- Upgrade simulations cover missing-hook detection, read-only diagnosis, start refusal, explicit recovery, installed state after recovery, and no acceptance shortcut for user edits.
- Full automation passed: `1498 passed, 4 skipped`; sdist/wheel build, isolated `site-packages` import of `4.0.15`, and CLI smoke all passed.

## Release assets

- `hermes-feishu-card-v4.0.15-macos.tar.gz`
- `hermes-feishu-card-v4.0.15-linux.tar.gz`
- `hermes-feishu-card-v4.0.15-windows.zip`
- `hermes-feishu-card-v4.0.15-checksums.txt`
