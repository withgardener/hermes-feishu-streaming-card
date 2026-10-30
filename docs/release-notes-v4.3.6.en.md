# Hermes Feishu Streaming Card V4.3.6

[中文](release-notes-v4.3.6.md) | [English](release-notes-v4.3.6.en.md)

V4.3.6 fixes Feishu `99992402` failures caused by unanchored topic delivery using the unsupported `receive_id_type=thread_id`, and adds configurable requester `@` mentions to approval/clarify interaction cards and completion notifications.

## Fixes

- Issue #237 / PR #238: the Feishu create API now always targets the parent `chat_id`; it no longer uses `thread_id` as either `receive_id_type` or `receive_id`. When `reply_to_message_id` exists, delivery still uses the reply API and preserves `reply_in_thread` semantics.
- The actual unanchored Gateway native-handoff create removes `thread_id` from adapter metadata so the Hermes fallback cannot repeat the same invalid request. Logical topic routing and stable UUID identity remain unchanged.
- `completion_notify.mention: false` no longer unconditionally requires a valid sender `open_id`. System/background turns can send a plain completion notification without an `@`; mention-enabled delivery still rejects missing, spoofed, or malformed identities.

## Added

- PR #228: pending approval/clarify cards and the opt-in completion notification can `@` mention the initiating user.
- `card.mentions_in_cards: false` is the master off switch. `card.interaction_mentions.approval`, `card.interaction_mentions.clarify`, and `card.completion_notify.mention` provide finer control. String booleans and profile/bot card overrides are normalized through the complete configuration-loading path.
- Both the schema 2.0 owner card and legacy auxiliary interaction cards can render mentions, without promoting a legacy card into the main PATCH owner.

## Safety Boundaries

- The original schema 2.0 streaming message remains the only PATCH owner. Legacy approval/clarify messages stay on their independent auxiliary rail, preventing a return of cross-card-dialect updates and `230099/200800`.
- An unanchored topic create lands in the parent chat rather than the original topic. Preserving topic placement still requires a real reply anchor and the reply API; this release does not guess or reverse-resolve an `omt_*` root message.
- The uncertain-warning throttling suggested in Issue #237 is outside this release. This cycle fixes only the confirmed invalid create request.
- Callback authentication, interaction ownership, Hermes patch ownership, delivery-UUID binding, and the archived `legacy/` runtime are not relaxed.

## Verification

- #237 regular-wheel isolated full pytest: **`3283 passed, 5 skipped`**; all 12 PR #238 CI checks passed; exact merge: `199d0390269693e74d1ff130cb7b4ecc4570dcfe`.
- #228 final-combination related units: **`225 passed`**; full server integration: **`324 passed`**; the two new completion regressions separately: **`2 passed`**; all 12 checks on the final rebased head passed; exact merge: `69f47123611bb1639e74d9a076212ce621322805`.
- v4.3.6 release candidate: `git diff --check` **passed**; full pytest in a fresh Python 3.12 regular-wheel environment **`3325 passed, 5 skipped in 560.94s`**; PEP 517 sdist/wheel, package/distribution `4.3.6` from isolated `site-packages`, the single Hermes plugin entrypoint, all 24 provenance slices, and the main CLI plus `enable/disable --help` are verified.
- Release PR CI, exact release merge, annotated tag, public tagged install, and Release assets/checksums: **pending**.
- Real Feishu: the Issue #237 reporter compared the API paths and observed `99992402` for invalid `thread_id` creation, success for `chat_id` creation and the reply API, and successful creates after a local hotfix. Independent maintainer client smoke in this cycle: **not run**; automated evidence is not represented as platform acceptance.

## Credits

Thanks @leavrcn for Issue #237's production metrics, Feishu API comparison, warning-flood analysis, and local-hotfix validation.

Thanks @Cassius0924 for implementing PR #228 and addressing the master-disable, cross-dialect ownership, and sender-less completion-notification boundaries through multiple review rounds.
