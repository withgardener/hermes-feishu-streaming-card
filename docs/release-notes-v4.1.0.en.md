# V4.1.0 Release Notes

Release date: 2026-07-28

V4.1.0 adds per-chat Hermes native delivery, lossless handling for excess tables, authenticated runtime-integrity monitoring, and explicit sidecar service management without implicit privilege escalation. Compatibility stays conservative: chats absent from `bindings.native_chats` keep streaming cards, existing configs without an `integrity` section load as `notify`, and `service.manager: auto` never enters system systemd.

## Choose cards or native delivery per chat

- `bindings.native_chats` accepts only exact, non-empty chat ids without control characters. Wildcard, regex, and prefix matching are rejected. Multi-profile setups read only `profiles.<profile_id>.bindings.native_chats` and never merge the top-level list.
- Use `chats use-native`, `chats use-card`, and `chats list` for atomic policy changes. Output shows masked summaries only. A change affects the chat's next new message and never flips an active turn.
- Before suppressing Hermes native output, the hook queries `POST /delivery/policy` with the domain-separated `hfc-policy-v1` proof. The sidecar checks again before creating a session or card. Timeout, authentication failure, broken configuration, or an unknown profile all fail open to Hermes native delivery.
- Answers, tools, approval/clarify, cron, system notices, command feedback, and pickers share the decision. `/hfc help/status/doctor/monitor` and the explicit smoke card remain card-based management surfaces.
- Multi-bot groups from Issue #162 are an explicit exception: an `@bot` added by a later streaming-card PATCH does not create a new `im.message.receive_v1` event. Put groups that require bot-to-bot triggering in `bindings.native_chats`, so the complete post carries the mention when it is created; the mentioned app also needs `im:message.group_at_msg.include_bot:readonly`, must keep its `im.message.receive_v1` subscription, and must publish a new app version after adding the permission so it takes effect. HFC never switches a live turn based on generated-answer content.

## Tables and card limits no longer silently lose content

- `card.table_overflow_mode: compact` is the default. A Markdown-aware scanner ignores fake tables inside fenced code and converts table six onward, in source order, to readable field lists while retaining every row and cell.
- Explicit `truncate` preserves the legacy “omit after five tables” behavior, but fenced code no longer consumes the limit and prose following a table is not removed.
- The final card JSON is checked through the same serializer against five rendered tables, 200 tagged elements, and a conservative 28,000-byte UTF-8 budget. A non-terminal overflow shows a small waiting card while collection continues. A terminal overflow never sends a partial answer: it returns a stable handoff descriptor. The short existing-card notice is a best-effort PATCH scoped to the current sidecar process; it neither blocks the native answer nor persists answer text or raw route identifiers.
- ACK capability is enabled only for the default profile after Hermes Base has produced final `text_content`, the delivery ledger has completed `record_obligation` / `mark_attempting`, stable-UUID wrappers are complete, the runtime delivery plan can be fingerprinted, and the turn has no attachment/media delivery. Hermes 0.19 startup recovery does not sweep independent secondary-profile ledgers, so secondary profiles explicitly retain ordinary native fail-open instead of claiming crash recovery. Gateway and sidecar negotiate only `native-ack-v2`, `stable-feishu-uuid-v2`, and `exact-base-delivery-v1`, and accept only an `hfc-native-handoff-v2` descriptor. The sidecar's private schema v4 persists obligation, exact-content, plan-fingerprint, canonical `create` / `thread-create` route, and a `target_hash` domain-separated across the default profile, chat, thread, and route. If any condition is missing, Hermes uses its ordinary random-UUID fail-open path; HFC never infers authority from raw completion text.
- An ACK-capable Gateway derives a stable Feishu UUID for every logical chunk from that descriptor. The Hermes delivery ledger persists `delivered` before the runtime sends a signed `hfc-native-handoff-ack-v1` confirmation to `POST /native-handoff/ack`. After a Gateway restart, `POST /native-handoff/recover` uses `hfc-native-handoff-recovery-v2` and recovers a pending descriptor only when obligation/content/plan/route/target all match; a hit sends the original ledger content without duplicating `RECOVERED_MARKER`. If the terminal POST committed in the sidecar but its response was lost or malformed, Gateway immediately performs the same five-fence recovery lookup to recover that descriptor. If both terminal and recovery responses are lost locally, the current send still uses the provisional UUID seed derived from the same five fences, then re-queries the complete descriptor asynchronously after the ledger marks `delivered`. If the original terminal request never reached the sidecar, later startup recovery still falls back to the visible-marker ordinary path, so HFC cannot claim exactly-once.
- ACK failure never rolls back the ledger. After the one-hour protocol window, the exact descriptor is no longer reused and the sidecar marks the record `uncertain`; upstream Hermes may still protect against answer loss through bounded native recovery with a visible `RECOVERED_MARKER`. That path uses an ordinary random UUID and never impersonates an exact retry. The protocol is effectively idempotent only within the window and does not promise forever exactly-once.
- This exact ledger-ACK contract covers only text-only ordinary final answers from the default profile through managed Hermes 0.19 Base. Secondary profiles and attachments/media keep Hermes' native best-effort delivery. Cron, direct-command, old-hook/new-sidecar, and incomplete-binding paths also remain ordinary native fail-open, never reuse the descriptor, and make no broader recovery claim.

## Integrity monitoring after Hermes upgrades

- New installations explicitly write `integrity.mode: safe`. Existing configs without the section load as `notify`, which reports but does not mutate. `off` disables the control plane without disabling ordinary event authentication or manual diagnostics.
- An older install can migrate only when Git ancestry, owned blobs, backup, manifest, anchors, and patch reversibility all verify:

  ```bash
  hermes-feishu-card integrity migrate-safe \
    --config ~/.hermes/config.yaml \
    --hermes-dir ~/.hermes/hermes-agent \
    --yes
  ```

  Success prints `sidecar.restart_required: true` and `gateway.restart_required: false`: restart the sidecar so the new mode takes effect, but do not restart the Gateway merely for this mode migration.
- The installed runtime sends signed `runtime.hello` / `runtime.heartbeat` events in the separate `hfc-runtime-v1` domain. `/health`, the CLI, and `/hfc` distinguish ready, starting, degraded, and restart-required state instead of equating process liveness with delivery readiness.
- `safe` executes only the existing patcher/recovery transaction under strict evidence. A successful repair reports `gateway.restart_required: true`, but HFC never restarts the Gateway automatically. The operator chooses a suitable window; a later matching `runtime.hello` clears the state. Incomplete evidence, user edits, symlinks, dirty targets, branch rewinds, source-stripped roots, or an unavailable authenticated control plane stay fail closed.

## Explicit sidecar service management

`service.manager` has four values:

- `auto`: probes only `systemd-user`; otherwise selects `detached`. It never reaches the system bus or invokes `sudo`.
- `systemd-user`: requires a working user manager and fails with remediation instead of silently falling back.
- `detached`: uses the existing owned detached process on macOS, Windows, containers, or when explicitly selected.
- `systemd-system`: an explicit Linux-only opt-in using transient `systemd-run --system`; it writes nothing under `/etc/systemd/system`, never invokes `sudo`, and fails when the caller lacks permission.

Docker Compose remains an ordinary setup, sidecar, and Gateway container stack. It pins `detached`, runs no systemd inside the image, and requests no privileged host integration. The CI setup container actually runs `install-docker.sh`, patches a fixture Hermes, and prepares shared-volume ownership; the sidecar, patched Gateway, and probe then run as non-root, wait for signed `runtime.hello` readiness, and send a real signed `POST /events` through the hook path. This is not a YAML-only check.

## Hermes compatibility boundary

Hermes 0.19.0 / the `v2026.7.20` series still imports `gateway.run.start_gateway` at Gateway runtime. V4.1.0 therefore retains the detectable, removable, restorable AST-owned `gateway/run.py` hook and makes `gateway/platforms/base.py` a third managed target under the same `manifest_version: 2`. Base receives only two minimal hooks: closure of no-independent-text paths and exact finalization after ledger attempting but before the native send. HFC does not copy or rerun Hermes' media-cleaning pipeline. Backups, writes, restore, and upgrade repair for run/base/optional cron are validated and rolled back together. A v1 manifest cannot prove Base ownership and must migrate only through strict repair/install verification. Authenticated heartbeats and strict repair handle upstream replacement; HFC does not install a broader import-hook bridge. Installed Hermes source is changed only through the official patcher/recovery transaction.

## Upgrade

```bash
export HFC_VERSION=v4.1.0
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```

Run `status` / `doctor --explain` after upgrading. Existing configs remain on `integrity.mode=notify`; opt into automatic safe repair only through `integrity migrate-safe`, then restart the sidecar. Any Gateway restart after a repair remains an operator decision.

The release workflow is expected to produce `hermes-feishu-card-v4.1.0-macos.tar.gz`, `hermes-feishu-card-v4.1.0-linux.tar.gz`, `hermes-feishu-card-v4.1.0-windows.zip`, and `hermes-feishu-card-v4.1.0-checksums.txt`. Actual assets, the public tagged install, and real Feishu acceptance are confirmed only after completion and are not claimed in advance here.

## Credits

- Thanks to @shutdown-awa for the per-chat card-exclusion request in Issue #157.
- Thanks to @Jasonsun77 for the reproduction and evidence of a hook removed by a Hermes fast-forward in Issue #158.
- Thanks to @Redeemer-w for reporting content loss after five tables in Issue #159.
- Thanks to @zyq2552899783-lgtm for the streaming-card PATCH versus native-post bot-to-bot mention evidence in Issue #162.
- Thanks to @Cyber-Yichen for the systemd environment observations in PR #156. V4.1.0 keeps explicit manager support but does not adopt an `auto` path that silently enters a system service or privilege boundary.
- Thanks to @wholegale39 for the newer Hermes entry-point investigation in PR #160. V4.1.0 uses the existing AST-owned hook, authenticated runtime monitoring, and strict repair instead of an import-time monkey patch.

These notes contain no real chat/message/user identifiers, credentials, transport secrets, local paths, or recovery fingerprints.
