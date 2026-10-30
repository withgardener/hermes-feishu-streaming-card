# V5.0.0: task reading, interaction continuity, and maintenance boundaries

V5 groups task reading, interaction continuity, per-turn metrics, and maintenance changes. Published availability is determined by the tagged GitHub Release and its verified assets.

## User-visible changes

- The opt-in `task` preset uses task sections, status headers, answer-first reading, and preserved execution history. Existing presets and explicit overrides remain unchanged. Use `card.timeline_expanded: false` to keep execution details collapsed by default.
- After a continuation is confirmed delivered, the previous task segment retains a blue handoff header and folds supported history. Unknown components or insufficient payload capacity retain the original content.
- A previous card can offer continuation navigation when the confirmed IM receipt provides a validated link or matching position metadata. A malformed nonempty link is rejected. Thread navigation requires matching thread position metadata; it does not fall back to the parent chat. When the acknowledgement has no usable navigation, the confirmed continuation message can be read once by its exact ID, with a 1.5-second and 64-KiB bound, no redirects and no retry. Only one undeleted, identity-matched message is accepted, and the current owner is checked again before patching. No chat history listing or message resend is introduced; unavailable metadata leaves the text fallback.
- Approval denials and timeouts retain their original execution authority. Natural clarify wait expiry updates display state without changing answers, exceptions, authorization, or execution. Unverifiable outcomes are not reported as execution success.
- Final cards show observed model/provider, elapsed time, input/output tokens, and context information. Missing values are omitted. Elapsed time includes interaction waits, and token totals cover the current turn's requests.
- Confirmed clarify delivery suppresses duplicate native questions for the same interaction. A bounded authenticated read-only check can recover a missing acknowledgement; unproven delivery retains native fallback. Arbitrary network failures are not claimed to be duplicate-free.
- `card-config --running` distinguishes loaded settings from next-load file settings. Unmatched process or scope identity is reported as unavailable. `--minimal-yaml` and offline previews share the same configuration rules.

## Runtime and installation

Event decisions, input normalization, receipt projection, terminal delivery, configuration, lifecycle I/O, and installer evidence have explicit owners. Execution identity, locking, authorization, and commit order remain with their original authorities.

Gateway terminal receipts survive normal, empty, and queued-result paths until the final native-send decision. Native text is suppressed only when the accepted card owns the unchanged result. Native tool progress uses the current turn, session, profile, and live owner. Results containing `MEDIA:` retain native attachment delivery; this path is not claimed to be duplicate-free.

The installer verifies actual PluginManager registration, including `post_api_request`, and refuses missing capabilities. Verified historical managed revisions support official restore followed by installation; unknown source drift remains rejected. Enable-command failure and configuration-ownership refusal have separate controlled diagnostics without exposing configuration contents.

Installation and restore share directory-bound I/O with identity checks, rollback, and cleanup error handling. Fixed Hermes v0.22.0 and main source compatibility snapshots are tested separately from actual Gateway runtime acceptance.

## Upgrade boundaries

Use the existing official setup/install and service-owner restart paths. Do not manually edit installed Hermes source. Native tables remain opt-in; oversized cells fall back to complete Markdown. Content and authorization scope must not be truncated. Existing Python support and public compatibility imports are retained.

Optional GPT subscription quota is shown only for an observed GPT turn using `openai-codex`; an API key, another model, or local login alone does not establish eligibility.

## Verification boundaries

Automated checks cover original Hermes tool/Gateway paths, signed HTTP interactions, ordinary-package provenance, managed patches, and exact restore. Full interpreter/platform matrices, the merge commit, annotated tag, assets, checksums, and public installation follow the [release playbook](wiki/release-playbook.md). Real Feishu execution, desktop display, phone display, and navigation clicks are separate evidence; unit tests do not establish human click acceptance. iOS and five-new-user trials are outside this delivery's acceptance scope and are not claimed as passed.

Actual Gateway acceptance on the fixed Hermes version is separate from source compatibility checks for latest stable/main. Split HOME/shared source and multi-Gateway layouts retain their existing ownership checks and refusal boundaries; the major version does not expand these support claims.

## Credits

Preserve previous contributor credits and original commit authorship. Native tables were contributed by [ywarmy](https://github.com/ywarmy) in [PR #391](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/391); see README and Git history for the complete record.
