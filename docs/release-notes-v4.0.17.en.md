# V4.0.17

V4.0.17 fixes lifecycle cross-wiring when parallel tools share the same name. Each invocation now uses Hermes' real `call_id`, keeping tool counts, query details, and durations aligned.

## Fixes

- The patcher wraps Hermes `tool_start_callback` and `tool_complete_callback` and pairs started/completed events with the stable call ID.
- Parallel `web_search` calls retain their own preview, arguments, status, and duration instead of repeating the second query on both rows.
- The “Reasoning & tools” count now tracks actual invocations; one tool's started/completed lifecycle counts once.
- The renderer removes every `耗时:` metadata line from the detail body and shows only the first valid duration on the compact headline, preventing a second duration from leaking into the detail footer.

## Compatibility and safety

- Existing Hermes start/complete callbacks are wrapped and still invoked; cached agents do not retain an HFC closure from the previous turn.
- Stable-ID mode is enabled only when the patcher validates compatible callback assignment and runtime-scope anchors.
- Older Hermes layouts without stable callback anchors keep the existing progress-callback fallback without expanding the patch surface or editing other Hermes files.

## Validation

- Regression coverage replays two parallel same-name `web_search` calls and verifies two independent rows, `2` tool invocations, and separate `2.12s` / `2.47s` durations.
- The current local Hermes original `gateway/run.py` backup compiles after patching, remains idempotent on reapply, and restores byte-for-byte through `remove_patch`.
- Full automation passed: `1508 passed, 4 skipped`; `git diff --check` passed.
- sdist/wheel, isolated `site-packages` import, public tagged install, release assets, and local runtime provenance are rechecked during release.

## Release assets

- `hermes-feishu-card-v4.0.17-macos.tar.gz`
- `hermes-feishu-card-v4.0.17-linux.tar.gz`
- `hermes-feishu-card-v4.0.17-windows.zip`
- `hermes-feishu-card-v4.0.17-checksums.txt`
