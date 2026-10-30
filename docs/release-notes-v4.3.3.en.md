# Hermes Feishu Streaming Card V4.3.3

[中文](release-notes-v4.3.3.md) | [English](release-notes-v4.3.3.en.md)

V4.3.3 fixes delivery continuity when Hermes explicitly asks to create a thread from the current Feishu message before a concrete `thread_id` is available. That placement is now bound to the active `CardSession` instead of being inferred again from later event identities.

## Fixed

- When Hermes sends explicit `reply_in_thread=true` with a verified `reply_to_message_id`, the first schema 2.0 streaming card creates the thread through the Feishu reply API. Ordinary, repeated, and runtime-admission clarify/approval cards retain the same anchor and placement.
- The opt-in completion notification reuses the session's `reply_in_thread` intent. Without a concrete `thread_id`, it still sends as a thread reply to that anchor instead of falling back to the top-level chat.
- `FeishuClient.send_text_message()` now matches the card-send boundary: either `reply_in_thread=true` or a non-empty `thread_id` requests thread placement, and either path fails closed without `reply_to_message_id` instead of posting top-level text. The default path with no thread-placement intent remains compatible.

## Safety boundaries

- The client reply path requires explicit thread intent and a non-empty reply anchor; a missing anchor is a rejection, not a best-effort top-level fallback. The server-side Hermes event path continues to accept only `om_` anchors.
- The original schema 2.0 streaming message remains the sole PATCH owner. Legacy interaction cards, callback tokens, chat/operator/profile binding, expiry, idempotency, Hermes patch ownership, and the archived `legacy/` runtime are unchanged.
- This release does not include PR #229's daemon-listener change: the `pytest-macos` required check timed out on the same subprocess test on two consecutive heads, and an author fix is still pending.

## Verification status

- Local regressions cover card/interaction/completion placement when the first reply has no concrete `thread_id`, plus the missing-anchor text-send path with no token lookup or Feishu API request.
- Local full pytest passed with **`3267 passed, 6 skipped`**. `git diff --check`, sdist/wheel builds, and a fresh Python 3.12 wheel-only provenance check covering the single Hermes plugin entry point, all 24 provenance slices, and CLI help smoke also passed.
- Remote Tests run `32657674121` (10 jobs) and CodeQL run `32657674120` passed for PR #232 candidate HEAD `f7de533d67f9e50afcd2c4d80fad89b572054605`.
- The exact merge SHA, public tag/install, Release assets/checksums, and real Feishu/Lark client acceptance are not yet complete for this release candidate. Automation is not represented as real-client evidence.

## Real Feishu acceptance still required

- From a top-level test-group message, trigger first-reply thread creation and confirm that the initial card, ordinary and runtime-admission interactions, and completion notification remain in one thread with no top-level fallback.
- Trigger explicit thread intent without an anchor and confirm that the completion notification posts no top-level text while only a sanitized rejection classification is recorded.
