# V5.0.3: Hermes compatibility, expired-interaction continuation and optional output rate

This release integrates [PR #438](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/438), [PR #436](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/436) and [PR #430](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/430), with additional fixes from independent review.

## Verified Hermes source compatibility

[#437](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/437) was an installation refusal after Hermes added channel-pin inheritance. Accept only the original expression and `event.internal or getattr(event, "inherit_channel_pin", False)`. Keep source/session/event bindings, complete tuples, assignment ordering and runner arguments strict. Unknown conditions, missing bindings and reassignment still refuse installation.

The source matrix uses full commits and file hashes; main is pinned to `0ab43d4f67e41be75f4f6c0fa14a86dbcfd3e5b3`. Detection, installation, repeat installation, diagnosis and byte-for-byte restoration are separate checks. This is compatibility with the pinned source, without a claim about later main commits or actual Gateway/model execution.

## Output after an expired interaction

When a clarify or approval card expires and Hermes falls back to a native text question below it, subsequent thinking, tools and answers use a continuation card below that question. Creation remains lazy: no new output means no empty continuation. The release also fixes the race where the sidecar expiry scan or event pre-check marks the interaction failed before the runtime failure event arrives.

Duplicate failures, late completions and unrelated interactions cannot revive old authorization. Closing an unanswered interaction at turn termination creates no extra continuation. Send failures and oversized content retain existing fallback and full-content handoff behavior.

## Optional completion-footer output rate

Append `output_rate` to the existing `card.footer_fields` list to enable phase one of [#392](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/392). It is absent from the default footer.

Use matching `usage.output_tokens` and timing from each Hermes `post_api_request`. Sum tokens and invocation windows separately, excluding tool/wait gaps. The stream window starts at the first accepted upstream stream event and ends with the request; role, reasoning or lifecycle events may be included, so this is not pure answer-token decode speed. Without a first stream event, use request duration, which can include TTFT and request-internal retries. Labels distinguish the approximate observation basis. Missing, malformed, tiny, MoA-aggregated or mixed model/provider samples are hidden. No text-length estimate is used.

Timestamp ordering, non-finite numbers, oversized integers and corrupt checkpoint rates are guarded. Values remain in the existing `tokens` mapping without a new checkpoint field. See [measurement semantics](wiki/observed-timing.md). Live streaming estimates are deferred.

## Upgrade and maintenance

Use the official installer for `v5.0.3`, preserving the original config, env, Hermes HOME and service ownership; see the [upgrade guide](upgrade-v4-to-v5.en.md). Current version defaults and bilingual documentation are synchronized. Ruff moves to 0.17.1, and official artifact/CodeQL Actions remain pinned to verified full commit SHAs. Package metadata remains authoritative for supported Python versions.

## Verification scope

Release gates include independent failing reproductions, focused regression, full preflight with a verified Git fixture, a separate pinned upstream matrix, real source hook-call contracts, Ruff/mypy, ordinary-wheel child processes, install/repeat/restore, the exact merge commit and tag CI. Official assets, checksums and isolated public-tag installation are checked after publication.

Real Feishu API, actual Gateway/model execution, desktop visuals, Android interaction and iOS are recorded separately; automated passes do not imply client acceptance. Issue #344 still lacks a complete reproduction, and #361 still needs real background-task evidence. Adjacent changes do not establish that those reports are resolved.

## Credits

Thanks to [Lite-G](https://github.com/Lite-G) for the implementation, reports and tests in #436 and #437 / #438; [Thxzzzzz](https://github.com/Thxzzzzz) for #430; and Dependabot for #388, #389, #390 and #439. Original commit authors, issue-evidence credits and all earlier contributions remain in Git history and both READMEs.
