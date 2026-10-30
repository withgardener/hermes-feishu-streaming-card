# Hermes Feishu Streaming Card V4.2.2

Release date: 2026-08-01

V4.2.2 fixes the visible-state gap in Feishu/Lark WebSocket private-chat `/update` confirmation cards. V4.2.1 could create a fully evidenced confirmation as the first message after Gateway restart, but after a button callback changed the durable operation to `cancelled` or `locking`, the new card existed only in the sidecar HTTP response. The Gateway background forwarder consumes only the `operation_id`, so it could not render that response back to Feishu. The original card therefore remained apparently actionable after cancel.

## Fix

- The native card action still returns its empty acknowledgement first, keeping Feishu API latency outside the WebSocket callback deadline.
- After acknowledgement, the sidecar asynchronously PATCHes the original confirmation message so visible and durable operation state agree.
- Cancel renders a terminal cancellation card and never schedules or starts the updater.
- Confirm attempts to render the locking/preparing transition before independent maintenance is scheduled.
- PATCH routing still uses the original delivery record and matching bot/profile. Missing inspection, delivery, or message evidence ends safely without guessing a destination.

## Unchanged safety boundaries

- Only an exact bare `/update` in a Feishu private chat enters the dedicated maintenance path. Group, non-Feishu, alias, and parameterized commands remain with Hermes' original handler.
- Initiator, chat, profile, target evidence, and the 120-second validity window remain bound.
- Tracked worktree state, incomplete Git operations, hook/integrity, active-work aggregation, drain marker, cached wheel, version, and final runtime verification remain fail-closed.
- Cancel itself does not run `hermes update` or mutate the Hermes checkout.

## Automation and real acceptance

- A new executor-facing regression creates a private update confirmation, POSTs the cancel action, waits for the background publisher to PATCH the original message, and asserts the terminal card text.
- The related operations/server/hook-runtime matrix reports `378 passed`.
- Full pytest reports `2307 passed, 5 skipped` on both Python 3.9 and 3.12. `git diff --check`, wheel/sdist, clean Python 3.12 `site-packages` package/distribution/CLI provenance, and an independent V4.2.2 maintenance runtime passed. PR CI and exact-merge-SHA verification continue in the release flow.
- After release, real Feishu acceptance sends `/update` as the first private-chat message after Gateway restart, clicks Cancel, and confirms the original card reaches its terminal cancelled state while Hermes remains unchanged and no updater runs.

## Install

```bash
export HFC_VERSION=v4.2.2
bash install.sh
```

After upgrading an existing installation, rerun the official `setup` / `install` flow so the Hermes runtime venv, managed hook, sidecar, and independent maintenance runtime all use V4.2.2. Do not edit `gateway/run.py` by hand.

## Release assets

- `hermes-feishu-card-v4.2.2-macos.tar.gz`
- `hermes-feishu-card-v4.2.2-linux.tar.gz`
- `hermes-feishu-card-v4.2.2-windows.zip`
- `hermes-feishu-card-v4.2.2-checksums.txt`

Verify downloaded files against `hermes-feishu-card-v4.2.2-checksums.txt`.
