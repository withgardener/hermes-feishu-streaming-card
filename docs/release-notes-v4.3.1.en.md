# Hermes Feishu Streaming Card V4.3.1

[中文](release-notes-v4.3.1.md) | [English](release-notes-v4.3.1.en.md)

V4.3.1 is a reliability hotfix for Hermes 0.20 Hybrid interactions and the v4.3.0 persistent service. It corrects more than the earlier “Feishu delivered no event” hypothesis. Follow-up evidence in Issue #216 exposed two local-chain failures: Hermes resumed after a button click but the card stopped showing streamed answer/reasoning updates, and the first explicit text-fallback reply did not wake the pending interaction.

## Issue #216: resume streaming after a click

- Pending clarify/approval now uses an interactive-card payload that the Feishu WebSocket card-action channel actually returns. Each button value carries only the constrained interaction id, choice, callback token, and exact profile identity.
- The Hermes hook carries that profile identity through both the action and context before forwarding to sidecar `/card/actions`, allowing the strict sidecar lookup to find the original profile/session instead of returning 404.
- The sidecar still wakes the original Hermes pending handle/future directly through the signed loopback runtime listener. Answer and reasoning deltas for the same turn continue onto the latest card after resolution without requiring another user message.
- Explicit `card.interaction_mode: text` declines runtime callback ownership before any session/interaction mutation, allowing Hermes' native numbered/text interceptor to consume the first reply without creating a second waiter.
- `/health` now reports sanitized runtime callback attempts, successes, failures, and last outcome categories without choices, callback tokens, chat/user/profile ids, or answer text.

## PR #226: persistent service enable

- Runtime identity validation now accepts the canonical `python-sha256:<64 hex>` value emitted by production code instead of permanently rejecting it as a non-`sha256:` identity.
- systemd `WorkingDirectory` uses path-value semantics instead of `ExecStart` argument quoting, while rejecting relative/control-character inputs and escaping `%` and backslashes to prevent specifier expansion or line continuation.
- Tokenless `/health` explicitly returns an empty `process_token_hash`; token-bearing processes return only SHA-256 and never echo the token. Persistent-service reconciliation no longer treats `None` and an empty string as drift.

## Real-environment evidence

- A candidate wheel was installed into fixed Hermes `v2026.8.3` / `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`, then exercised through the local Hermes Gateway and a real Feishu WebSocket long connection.
- Two physical button clicks reached the sidecar runtime listener and resolved successfully. The card then displayed the next streamed result without requiring an extra message.
- Real identifiers, callback tokens, credentials, answer text, and screenshots are not stored in the repository or release notes.

## Compatibility and safety boundaries

- Fixed-tag capability proof, 17 Hybrid patch groups, seven targets, V3 installer ownership, and byte-for-byte restore remain mandatory.
- Callbacks remain bound to the exact session, profile, interaction, operator/chat, and expiry. Duplicate, conflicting, expired, wrong-profile, and unknown descriptors fail closed.
- `legacy/` remains a read-only archive, and PR #203 is not part of the active runtime.

## Contributors

- Thanks to [saulgoodmanngabriel](https://github.com/saulgoodmanngabriel) for [Issue #216](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/216), and to [zhangzq](https://github.com/zhangzq) for the Hermes 0.20 retest that separated “click does nothing” into “runtime resumed but streaming/reasoning updates disappeared” plus a first-reply text-fallback wakeup failure.
- Thanks to [RanHuang](https://github.com/RanHuang) for [PR #226](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/226), which identified the runtime-identity, systemd `WorkingDirectory`, and tokenless-health reconciliation root causes. The final implementation retains those findings with stricter path escaping and adversarial regression coverage.
- This cycle also reconciles both README contributor sections against historical releases, PRs, issues, commits, and co-author trailers, restoring omitted code authors, proposal authors, issue reporters, and real-environment testers. GitHub's Contributors graph includes commit history only; issue/comment-only contributions remain credited in README and release notes.

## Verification

- Full pytest: `3245 passed, 6 skipped in 425.58s`.
- `python -m build --no-isolation` produced `hermes_feishu_streaming_card-4.3.1.tar.gz` and `hermes_feishu_streaming_card-4.3.1-py3-none-any.whl` successfully.
- A fresh Python 3.12 venv installed only the candidate wheel and public dependencies. Package/distribution versions were both `4.3.1`, import origin was inside that venv's `site-packages`, exactly one Hermes plugin entrypoint was present, all 24 provenance slices were packaged, and the main CLI plus `enable/disable --help` exited 0.
- `git diff --check`, exact merge SHA, remote CI, annotated tag, public tag/install, and Release assets are recorded during publication and are not marked passed beforehand.
