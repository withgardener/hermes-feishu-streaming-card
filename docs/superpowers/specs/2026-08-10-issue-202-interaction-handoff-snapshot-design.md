# Issue #202 Interaction Handoff Snapshot Design

## Summary

When `interaction.requested` arrives for an existing streaming-card session,
HFC sends a fresh interaction card and promotes its Feishu message id as the
target for later updates. The predecessor card is intentionally retained as a
history snapshot, but it is never finalized. If the active runtime header was
`正在使用 clarify`, that transient state remains visible forever and repeated
clarify rounds leave multiple apparently stuck cards.

HFC will finalize the predecessor only after the replacement interaction card
has been delivered successfully. The predecessor becomes a green, read-only
snapshot whose header and quote summary say `已转入交互卡片`; its existing
answer, reasoning, and tool history remain available, while transient runtime
header text is removed. The replacement remains the only interactive and
subsequently updated card.

This change will ship as v4.2.11. Automated maintainer verification is the
release gate; Issue #202 reporter confirmation is requested after release but
is not a prerequisite for publishing a fully green candidate.

## Problem And Invariants

The current promotion sequence is:

1. Apply `interaction.requested` to the canonical `CardSession`.
2. Render and send a new interaction card.
3. Replace `FEISHU_MESSAGE_IDS_KEY[session_key]` with the new message id.
4. Cancel the prior animation task and continue all later updates on the new
   card.

The old card is no longer authoritative after step 3, so no later event can
clear its runtime subtitle. This violates the user-visible meaning of a
history snapshot even though interaction delivery itself succeeds.

The fix must preserve these invariants:

- The new card is sent instead of adding buttons to an older message.
- A failed new-card send restores the request-time session snapshot and leaves
  the old card authoritative and retryable.
- The canonical session and interaction result remain unchanged by the
  predecessor-only rendering operation.
- Unknown or failed Feishu update paths remain fail-open for the Hermes
  Gateway; a cosmetic predecessor update cannot invalidate an already
  delivered interaction.
- Callback authentication, chat binding, interaction expiry, sequence
  idempotence, topic/reply routing, and native gray-text suppression do not
  change.
- `legacy/` and the Hermes patch surface do not change.

## Considered Approaches

### A. Finalize The Predecessor After Replacement Delivery

Send the new interaction card first. Once delivery succeeds, stop the old
animation, render a detached final snapshot from the pre-request session, PATCH
the predecessor, and then promote the new message id.

This is the selected approach. It preserves the bottom-of-chat interaction
behavior introduced for Issue #187, has no migration or configuration burden,
and limits the new behavior to the exact successful-promotion boundary.

### B. Restore In-Place Interaction Rendering

PATCH the existing card with buttons instead of sending a new card. This would
avoid predecessor snapshots, but it would regress Issue #187: later choices
could appear far above the active conversation and repeated interactions would
reuse stale visual positions.

This approach is rejected.

### C. Add A Configurable Promotion Strategy

Add a setting that selects in-place rendering or new-card promotion. This is
more flexible, but it duplicates lifecycle behavior, expands documentation and
test matrices, and makes the default bug remain a policy choice.

This approach is rejected for v4.2.11. A future configuration is justified
only if users demonstrate a separate need after the predecessor lifecycle is
correct.

## Selected Data Flow

The successful `interaction.requested` path remains inside the existing
session lock:

1. Keep the existing deep copy of the pre-request `CardSession` as rollback and
   predecessor evidence.
2. Apply the event and render the canonical interactive card.
3. Send the new interaction card with the existing unique interaction delivery
   key.
4. If the send fails, restore the canonical snapshot and return the current
   `502`; do not cancel animation or touch the predecessor.
5. If the send succeeds, remove and cancel the predecessor animation task and
   await its cancellation before any final PATCH. This prevents a queued
   animation frame from overwriting the final snapshot.
6. Build a detached predecessor snapshot from the pre-request copy:
   - preserve conversation/message/chat identity, visible answer/thinking text,
     attachments, timeline, tool history, and the prior completed interaction
     result when one exists;
   - clear `latest_tool_preview` and `runtime_phase_text`;
   - set explicit `display_status` to `completed` without marking the canonical
     turn terminal;
   - render through the existing per-session card configuration;
   - replace the rendered header subtitle and quote summary with
     `已转入交互卡片` and keep a green completed template;
   - never include the new pending interaction buttons or callback token.
7. PATCH the old message through the existing retrying update helper. A false
   result is recorded through existing update metrics and diagnostics but does
   not change the successful interaction response.
8. Promote the new message id, store the interaction result, and start a fresh
   animation task for the new card.

For a second or later clarify round, the then-current card follows the same
sequence. Therefore every predecessor receives at most one finalization for
the applied event and only the newest card stays interactive.

## Component Boundaries

### `hermes_feishu_card/server.py`

Add one small helper that receives the application, session key, old message
id, bot id, rollback snapshot, and old animation task. It owns animation
cancellation, detached snapshot rendering, the `已转入交互卡片` presentation
override, and the best-effort PATCH.

The event handler remains responsible for transactional ordering: replacement
delivery must succeed before the helper runs, and message-id promotion happens
after predecessor finalization has been attempted.

### `hermes_feishu_card/session.py` And `render.py`

No persistent session field or public rendering mode is added. The handoff
state exists only in a deep-copied `CardSession`, and the final presentation
override is applied to the rendered card owned by the helper. This keeps the
canonical session model and all later rendering unchanged.

### Metrics And Diagnostics

Use the existing `feishu_update_attempts`, successes, failures, retries,
latency, and sanitized `last_update_error` path. No new public metric is needed
because the operation is an ordinary Feishu card PATCH and the existing
diagnostic already distinguishes send from update failure.

## Failure And Concurrency Behavior

- Replacement send failure: restore the canonical session and preserve the old
  animation/card exactly as today.
- Animation cancellation: cancellation is awaited before final PATCH; a
  cancellation exception is consumed and cannot fail interaction delivery.
- Predecessor PATCH failure: retry through the existing bounded update helper,
  retain sanitized diagnostics, then continue promotion and return success.
- Duplicate or stale event: existing sequence checks prevent another send or
  predecessor finalization.
- Callback arriving immediately after send: the session lock prevents callback
  mutation from interleaving with promotion/finalization.
- Process shutdown during finalization: the new interaction has already been
  delivered, so no rollback attempts to delete or invalidate it. The operation
  remains fail-open and recovery does not invent a second card.

## Test Design

The change is implemented test-first with these acceptance cases:

1. A running clarify/tool header on the original card is replaced by a green
   `已转入交互卡片` predecessor after successful interaction delivery.
2. The predecessor retains pre-request visible content and tool history but
   contains no pending button, callback token, or transient runtime subtitle.
3. The replacement card still contains the prompt/buttons and receives the
   completed selection plus all later answer updates.
4. Two consecutive interactions finalize the first two cards once each and
   leave only the third/newest card pending.
5. A replacement send failure leaves the old card and animation untouched and
   the same event remains retryable.
6. A predecessor PATCH failure still returns a successful interaction response,
   promotes the replacement, and increments existing update-failure evidence.
7. A delayed animation task cannot overwrite the finalized predecessor after
   cancellation.
8. Existing interaction expiry, callback security, form submit, text fallback,
   reply/topic routing, and promotion rollback tests remain green.

Focused verification runs the session/render/server/clarify matrices. Release
verification then runs full pytest and `git diff --check` on the candidate and
again on the exact merge SHA before the annotated v4.2.11 tag. The tag-triggered
release workflow, checksums, and public `site-packages` installation must pass
before Issue #202 receives the final upgrade instructions.

## Documentation And Release Scope

Update the interaction lifecycle in `docs/wiki/event-flow.md` and add the
predecessor-finalization case to `docs/wiki/feishu-acceptance.md`. v4.2.11
release notes describe the old-card visual fix, the fail-open update boundary,
and the exact verified release evidence. No unrelated refactor, new config
option, or Hermes patch change is included.
