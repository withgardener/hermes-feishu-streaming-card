# Event Protocol

[中文](event-protocol.md) | [English](event-protocol.en.md)

The minimal Hermes hook sends message lifecycle events to the sidecar. The hook runtime converts recognizable Hermes message context into `SidecarEvent` JSON and sends it fail-open to the local sidecar `/events` endpoint. The sidecar depends on event semantics, not on Feishu logic inside the Hermes process.

## Events

| Event | Description |
| --- | --- |
| `message.started` | A new message starts; the sidecar creates or initializes a card session. |
| `thinking.delta` | Incremental model thinking content; the sidecar accumulates and displays it while streaming. |
| `tool.updated` | Tool call status changes; the sidecar updates tool call counts and status in the card. |
| `answer.delta` | Incremental final-answer content; the sidecar accumulates answer text until completion. |
| `message.completed` | The message completes successfully; the card switches to `已完成` and final answer content replaces thinking content. |
| `message.failed` | The message fails; the card stops streaming and shows a public failure state or summary. |
| `interaction.requested` | Hermes needs user approval or a choice. The sidecar renders buttons or numbered text choices in the same card and exposes pending state through `/interactions/{interaction_id}`. Responses include `interaction_mode`; in `text` mode the hook immediately falls back to Hermes' native text interaction path. |
| `interaction.completed` | A card button was clicked. The sidecar updates the original card with the selected option and lets the Hermes hook poll the result to continue. |
| `interaction.failed` | The interaction failed or timed out. The sidecar preserves the failed state and the Hermes hook can fail open to native Hermes behavior. |

`interaction.requested.data.allow_custom_input` explicitly declares whether the interaction accepts content outside the supplied options. When `true`, the card renders an Other input; when `false`, it renders only the fixed options supplied by Hermes. The hook emits `true` for Clarify interactions and defaults to `false` for approvals, keeping approval cards aligned with Hermes' native UI. For legacy events without this field, only `kind=clarify` defaults to custom input.

## Routing Fields

All events keep the required `conversation_id`, `message_id`, and `chat_id` fields. From V3.6.4, events may also carry an optional `thread_id`; when it represents a Feishu `om_` / `omt_` thread context, the sidecar uses the Feishu reply API to create the initial card in the same thread where the user sent the message. Later updates still PATCH the created card message.

When Hermes only has the intent to create a thread from the current message and no concrete `thread_id` yet, the hook may send `data.reply_in_thread=true` together with `data.reply_to_message_id`. The sidecar keeps this intent in the current `CardSession`, so later approval/clarify cards and deferred runtime-admission deliveries continue using the same reply API and anchor instead of falling back to the chat top level.

`turn_id` is optional and provides the stable identity of one Agent turn. `message_id` remains the identity of the current event, stream, or reply, while `data.reply_to_message_id` is only the Feishu reply anchor. When `turn_id` is present, session ownership, event ordering, delivery policy, and native handoff use it and never let a `reply_to_message_id` alias change the owning turn.

When `turn_id` is absent, the sidecar preserves the legacy fallback: `message_id` is the turn identity and later stream events may still use a `reply_to_message_id` alias to reach an existing active session.

## Card States

Normal card states are intentionally simple:

- `思考中` (thinking)
- `等待选择` (waiting for choice)
- `已完成` (completed)

During `思考中`, the card shows accumulated `thinking.delta` content and real-time tool call counts. When `interaction.requested` arrives, the card enters `等待选择`. The default `auto` mode receives button clicks through the Hermes Feishu adapter's WebSocket-native card-action channel and forwards them to sidecar `/card/actions`, so localhost/private sidecars need no public callback URL. Numbered choices and Hermes' native text interaction path are used only when `text` is configured explicitly. Since V3.8.5, independent commands such as `/new`, `/reset`, and `/model` use the same Feishu/Lark WebSocket-native card-action path, and direct execution results stay in cards too. After `message.completed`, the card enters `已完成`, the final answer replaces thinking content, and users no longer need to see the full thinking trace in the completed state.

## V4.1 Control Protocols And Domain Separation

V4.1 adds mutually isolated local control planes beside the `/events` data plane. Each action uses a distinct signing domain:

| Endpoint | Purpose | Signing domain | Failure behavior |
|---|---|---|---|
| `POST /events` | Message lifecycle and card data plane | event domain | Hermes stays on native fail-open until card ownership is confirmed |
| `POST /delivery/policy` | Per-chat decision before the hook suppresses native output | `hfc-policy-v1` | Timeout, invalid/replayed proof, config error, or unknown profile returns to native delivery |
| `POST /runtime/events` | `runtime.hello` / `runtime.heartbeat` readiness | `hfc-runtime-v1` | Hermes work continues; sidecar readiness degrades and no source mutation is authorized |
| `POST /native-handoff/recover` | Exactly match a pending descriptor by obligation/content/plan/target hashes and canonical route | `hfc-native-handoff-recovery-v2` | Any fence mismatch returns not found; Hermes preserves its recovered marker and random-UUID fail-open path |
| `POST /native-handoff/ack` | Confirm the native final after every chunk succeeds and the ledger is `delivered` | `hfc-native-handoff-ack-v1` | ACK failure never rolls back a delivered ledger; sidecar pending state eventually becomes uncertain |

Policy, runtime, native-recovery, and native-ACK proofs bind the exact raw body, a short timestamp window, and nonce replay protection. Recovery carries only 64-character obligation/content/plan/target digests and a `create` / `thread-create` enum, never answer text or a reply anchor. Responses never echo a chat id, transport root, path, source hash, or recovery fingerprint. `runtime.hello` / `runtime.heartbeat` carry only schema-bounded generation/package/sequence facts. Strict repair separately verifies Git, manifest, backup, blobs, anchors, and a fresh pre-mutation fingerprint.

Exact native handoff also requires Gateway and sidecar to advertise `native-ack-v2`, `stable-feishu-uuid-v2`, and `exact-base-delivery-v1`, with descriptor protocol `hfc-native-handoff-v2`. If the terminal POST response is lost or malformed, Gateway immediately performs a recovery-v2 lookup with the same obligation/content/plan/route/target five-fence binding. If that lookup response is unavailable too, the current send may use the provisional UUID seed derived from those same fences, but ACK still requires recovery of the complete descriptor. If the original request never reached the sidecar, later delivery remains visible-marker ordinary native fail-open and no uncertain result is represented as exact success. This contract covers only text-only ordinary final answers from the default profile through managed Hermes 0.19 Base; secondary profiles never advertise exact ACK.

A turn's delivery decision is pinned on its first event. A `bindings.native_chats` change affects only the next new message, and a duplicate terminal event cannot send once through cards and once natively. The sidecar checks policy again before creating `CardSession`, so hook preflight and server enforcement are both required.

## Content Safety

The sidecar must filter internal thinking boundaries and must not expose `</think>` or similar control tags. Final answers should come from public response content, not raw internal streams.

The protocol and card behavior are guarded by fake client, fixture Hermes, mock sidecar, Feishu callback simulation, and real Feishu smoke coverage.
