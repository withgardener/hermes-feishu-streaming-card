# V4.0.2

V4.0.2 is an installer-upgrade hotfix for V4.0.1. It retains the #106 native media-text deduplication fix and safely upgrades verified older owned hooks to the current renderer.

## Fixes

- When current `run.py` and its backup both match the install manifest, owned markers remove cleanly back to that backup, and the new hook validates in memory, the recovery planner now executes `reapply_current_hook`.
- Fixes `run.py changed since install; refusing to repair` for a real V4.0.0 installed-hook upgrade state.
- User edits, current/backup hash mismatches, invalid backups, corrupt markers, and unsupported new anchors remain fail-closed and are never overwritten.

## Added

- Implements issue #107's opt-in `subscription_usage` footer. Once included in `footer_fields`, the plugin uses Hermes runtime native `fetch_account_usage("openai-codex")` and renders remaining quota in the `5h 26% · weekly 89%` style.
- It remains disabled by default, stores no account data, and passes no credentials in command arguments. Older Hermes versions, missing login, network errors, or a five-second timeout silently omit the field without affecting card completion.
- Thanks to @tianqiii for the requirements, Hermes-native API direction, and display format.

## Also included

- The V4.0.1 fix for [issue #106](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/106): after a card succeeds, native delivery receives media directives only, without a duplicate copy of the answer already displayed in the card.
- Completed cards hide `MEDIA:` and internal local paths while Hermes continues native image/file delivery.
- Thanks to @ShakuOvO for reporting #106 and @blakejia for independently confirming it on Hermes `0.18.2`.

## Verification

- Recovery/install regression matrix: `121 passed`.
- Server/render/subscription-usage focused matrix: `237 passed`.
- Real local V4.0.0 owned-hook upgrade: the current hook was reapplied automatically, doctor reported a complete and consistent install state, and Gateway plus sidecar resumed.
- Read-only local Hermes native Codex account-usage verification returned and formatted both Session and Weekly windows.
- Full suite: `1266 passed, 3 skipped`; `git diff --check` passed.
- Local package: the sdist and wheel built successfully, and a clean venv imported version `4.0.2` from `site-packages`.

## Release assets

- `hermes-feishu-card-v4.0.2-macos.tar.gz`
- `hermes-feishu-card-v4.0.2-linux.tar.gz`
- `hermes-feishu-card-v4.0.2-windows.zip`
- `hermes-feishu-card-v4.0.2-checksums.txt`
