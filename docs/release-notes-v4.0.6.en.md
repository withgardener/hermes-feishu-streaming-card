# V4.0.6

V4.0.6 fixes three connected Hermes 0.18.x reliability gaps: streamed turns no longer stay generating because the completion hook sits after an early return, background-process and `/background` running/final notifications update stable Feishu cards, and a real Hermes source replacement has an explicit, verified, fail-closed recovery path.

## Hermes 0.18.x completion

- Issue #120 / PR #121 installs the `message.completed` hook before the `agent_result.already_sent` early return.
- Terminal events explicitly use the same reply anchor as started/delta events instead of an ambiguous terminal fallback message id.
- The queued-completion hook scans across the newer multiline `_stream_confirmed_final_delivery(...)` call and is no longer silently omitted.
- Previous owned completion blocks remain recognized and migratable; apply, AST parse, remove, and repeated apply stay verifiable and idempotent.

## Background notice cards

- PR #119 converts background-process and `/background` running/final envelopes into `system.notice` events.
- One background task keeps a stable notice identity and updates one card from running to terminal state, while concurrent tasks remain separate.
- Hermes' immediate `Background task started` envelope is also claimed by the card runtime. Anchored background-task notices use an independent lifecycle, so the same card reaches terminal state without a gray start reply or a lingering `Generating` footer.
- Topic/thread routing, Gateway sequence resets, duplicate task output, and terminal retry/controller cleanup have explicit boundaries.
- Card failure keeps the native fail-open path so a plugin failure does not become a Hermes workflow failure.

## Recovery after a Hermes upgrade

- Issue #118 adds `--accept-hermes-upgrade` to `repair`, `install`, and `setup`.
- Recovery still refuses by default when current Hermes source differs from the verified backup. It proceeds only after the user confirms an intentional upgrade and passes `--accept-hermes-upgrade --yes`.
- Recovery clears only verified stale HFC manifest/backup artifacts; it never restores the old backup over upgraded Hermes source. Installation then backs up and patches the current source.
- Missing or corrupt backups, invalid manifests, symlinks, unreadable files, unknown markers, unsupported anchors, and remaining owned patches are still refused.

## Credits

- Thanks to @nasvip for issue #118's complete upgrade reproduction and refusal output.
- Thanks to @hzy for PR #119's background notice-card implementation.
- Thanks to @lRoccoon for issue #120's production diagnosis and PR #121.

## Validation

- Full automated release gate: `1315 passed, 3 skipped`; `git diff --check` passed.
- Issue #118 temporary Hermes sandboxes passed six focused paths: default refusal, explicit acceptance, Gateway+cron upgrade, and corrupt-backup refusal.
- The sdist and wheel built successfully; a clean Python 3.12 venv imported version `4.0.6` from the wheel.
- A local Hermes 0.18.2 runtime was upgraded from 4.0.4 to 4.0.6; `COMPLETE` and `QUEUED_COMPLETE` markers, runtime import, and `doctor --explain` all passed.
- Real Feishu E2E passed on 2026-07-15: private completion, private `/background`, test-group @bot completion, and group-thread `/background` all reached the expected terminal state. Thread routing stayed in the original topic, no gray native start/final answer was emitted, the terminal background card no longer showed `Generating`, and sidecar send/update failures remained zero.

## Release assets

- `hermes-feishu-card-v4.0.6-macos.tar.gz`
- `hermes-feishu-card-v4.0.6-linux.tar.gz`
- `hermes-feishu-card-v4.0.6-windows.zip`
- `hermes-feishu-card-v4.0.6-checksums.txt`
