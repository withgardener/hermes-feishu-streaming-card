# Issue #227 Card Rail Handoff Design

## Status

Approved problem and direction: Bailey asked to reply to Issue #227 and begin the fix after reviewing the maintainer diagnosis. This document refines the implementation so it preserves the existing schema 2.0 streaming card instead of introducing a third successor message.

## Problem

V4.3.1 sends a pending clarify or approval as a legacy interactive card because Feishu's WebSocket `p2.card.action.trigger` path requires the legacy `action` container. After the user selects an option, the same Feishu message is treated as a schema 2.0 streaming card in two places:

1. The sidecar PATCHes the completed schema 2.0 render to the legacy interaction message.
2. The Gateway callback returns that schema 2.0 render as a raw callback card.

Issue #227 demonstrates that the callback transition can fail with `200673`, while the message PATCH transition can fail with `230099` / `200800`. A toast-only callback removes the first failure but leaves the second transition unchanged.

## Constraints

- A Feishu message keeps one card dialect for its lifetime.
- `FEISHU_MESSAGE_IDS_KEY` continues to identify the authoritative schema 2.0 streaming card.
- The legacy interaction message is an auxiliary input surface and is never a streaming PATCH target.
- The callback response never contains a schema 2.0 raw card.
- Hermes runtime resolution, profile/chat/operator/token/expiry validation, and fail-closed interaction ownership remain unchanged.
- Unknown or unsupported non-HFC callback paths remain fail-open to Hermes.
- `legacy/` and the Hermes patch surface are not changed.
- No real identifiers, callback tokens, credentials, response bodies, or URLs enter logs, tests, or documentation.

## Considered Approaches

### A. Toast-only callback

This removes `200673` but leaves the legacy interaction message as the authoritative streaming message. The next schema 2.0 PATCH still crosses card rails and can fail with `230099` / `200800`. Rejected as incomplete.

### B. Promote a new schema 2.0 successor after every click

This gives subsequent streaming a valid v2 target, but it adds a third message, creates a send-before-delta race after Hermes is unblocked, and requires failure recovery if the successor send fails. Rejected because an existing v2 streaming card is already available.

### C. Keep the schema 2.0 streaming card authoritative and use a legacy auxiliary interaction card

Recommended. On `interaction.requested`, HFC sends the legacy interactive card but does not replace `FEISHU_MESSAGE_IDS_KEY`. The existing v2 card is frozen into its current "已转入交互卡片" snapshot. On selection, HFC PATCHes the completed/current render back to that same v2 card and returns a completed legacy card through the callback response so the clicked auxiliary card also closes in place.

This preserves two fixed rails:

- Main streaming message: schema 2.0 create and schema 2.0 PATCH only.
- Auxiliary interaction message: legacy create and legacy callback replacement only.

## Architecture

### Interaction request

1. The session already owns a schema 2.0 Feishu message through `FEISHU_MESSAGE_IDS_KEY`.
2. `interaction.requested` renders and sends a legacy card containing callback buttons or forms.
3. The existing schema 2.0 message is updated with the read-only "已转入交互卡片" snapshot, using the existing predecessor-finalization helper.
4. `FEISHU_MESSAGE_IDS_KEY` is not changed to the legacy message ID.
5. No animation or streaming flush controller targets the legacy message.

The same ownership rule applies to normal interaction delivery and runtime-admission delivery.

### Successful selection

1. The Gateway validates and forwards the legacy action to `/card/actions` exactly as in v4.3.1.
2. The sidecar resolves the Hermes pending handle before terminal interaction mutation, preserving current runtime semantics.
3. `interaction.completed` updates the authoritative schema 2.0 message referenced by `FEISHU_MESSAGE_IDS_KEY`.
4. `/card/actions` returns a separate legacy completed-card render containing the selected label and no button, callback token, or interaction credential.
5. The Gateway wraps only that legacy card as the raw Feishu callback response. Because the callback card has no `schema` or `body`, the response does not attempt a schema 2.0 callback transition.
6. Later answer/thinking/tool events continue PATCHing the original schema 2.0 message.

### Failed or expired selection

- A late click returns a legacy failed-card callback with the sanitized interaction error and warning status.
- The authoritative schema 2.0 card receives the same failed/expired state through its normal PATCH path.
- Periodic expiry can update the schema 2.0 owner without attempting to PATCH the auxiliary legacy message. The auxiliary card may remain visually pending until a late click returns the failed callback card; adding a separate CardKit/interactive-card update API is outside this fix.

### Missing schema 2.0 owner

The normal Hermes and Hybrid paths create `message.started` before an interaction. If a callback-mode `interaction.requested` arrives without an existing Feishu message owner, the existing fail-open behavior is preserved for this patch; the implementation must not invent a cross-dialect PATCH target. A dedicated direct-interaction bootstrap can be designed separately if a real supported producer is identified.

## Component Changes

### `hermes_feishu_card/render.py`

- Extend the internal legacy interaction renderer to produce pending, completed, and failed callback cards.
- Expose one narrow renderer for server callback responses.
- Completed and failed legacy renders remove all interactive controls and credentials.

### `hermes_feishu_card/server.py`

- Stop promoting the legacy interaction delivery ID into `FEISHU_MESSAGE_IDS_KEY` in both standard and runtime-admission delivery paths.
- Keep the existing schema 2.0 message as the flush/update owner.
- Return the legacy completed/failed render from `/card/actions`, while internal streaming updates continue to use the normal schema 2.0 render.
- Preserve interaction result storage, runtime listener ordering, retry boundaries, metrics, and predecessor snapshot behavior.

### `hermes_feishu_card/hook_runtime.py`

- Continue using the raw callback response helper only for a sidecar-provided legacy card.
- Add a defensive dialect check: a schema 2.0 card from the sidecar must not be attached to a Feishu interaction callback. It falls back to a success toast for a resolved interaction so a future server regression cannot reintroduce `200673`.
- Apply the same rule to direct selection and form-submit success paths.

## Error Handling

- If the auxiliary interaction send fails, do not change the authoritative v2 message ID; preserve current rollback/retry behavior.
- If the v2 snapshot PATCH fails after the legacy interaction send succeeds, the legacy interaction remains usable and failure stays in existing sanitized update diagnostics.
- If the post-selection v2 PATCH fails, the callback still returns a valid legacy completed card and Hermes remains resolved; existing bounded update metrics record the main-card failure.
- If the sidecar accidentally returns schema 2.0 callback data, the Gateway returns a success toast instead of a raw card.
- Callback failures never roll back a Hermes choice that has already resolved.

## Test Strategy

### Render tests

- Pending legacy card contains callback controls and no schema 2.0 fields.
- Completed legacy card contains the selected label, no controls, and no callback token.
- Failed legacy card contains the sanitized error and no controls.

### Server integration tests

- A dialect-aware Feishu fake records the dialect used when each message is sent and rejects any PATCH whose dialect differs.
- `interaction.requested` keeps the original schema 2.0 message ID as the authoritative owner.
- Selection updates the original v2 message, never PATCHes the legacy auxiliary message, and returns a legacy callback card.
- Runtime-admission, form submit, expiry, repeated interaction, predecessor snapshot failure, and update failure keep their existing security and fail-open/fail-closed contracts.
- Subsequent answer/thinking updates remain on the original schema 2.0 message.

### Gateway unit tests

- Legacy callback cards are returned as raw cards.
- Schema 2.0 callback cards are rejected and replaced with a success toast.
- Form-submit and direct-select success use the same dialect gate.

### Real Feishu acceptance

- Hermes 0.20 + `lark-oapi==1.6.8`, WebSocket long connection, current mobile and desktop clients.
- Direct choice and custom-input form both resolve Hermes.
- No client `200673` popup.
- `/health` adds no `230099` / `200800` update failure.
- The legacy interaction card shows the completed selection.
- The original schema 2.0 card resumes answer/thinking streaming and reaches terminal state without another user message.

## Non-Goals

- Fixing unrelated empty-value callbacks that fall through to Hermes `/card` synthesis.
- Adding a new Feishu CardKit entity/update API.
- Changing text-mode interaction behavior.
- Version bump, release, deployment, or closing Issue #227.
