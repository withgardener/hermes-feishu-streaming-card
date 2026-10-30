# V3.8.8 System Notice Cardification Plan

## Goal

Hermes native system/status notices that currently appear as grey Feishu text messages should be rendered through the streaming-card experience:

- If the current Hermes turn has an active card, merge the notice into that card's auxiliary timeline.
- If there is no active/updatable card, send a compact independent notice card.
- Preserve native Feishu text fallback when the sidecar is unavailable.

## Scope

Target notices for this release:

- Long-running heartbeat, for example `Working - 2 min - iteration 1/90, terminal`.
- Context/compression notices, for example Codex context cap or auto-compaction changes.
- Automatic session reset notices.
- Skill loading notices.
- Self-improvement review notices.

Out of scope for V3.8.8:

- Reworking Hermes core message semantics.
- Replacing all normal assistant replies with notice cards.
- Docker operational redesign, except keeping behavior compatible.

## Version Split

- V3.8.8: notice cardification, tests, and local Hermes smoke.
- V3.9: Docker and deployment ergonomics.
- V4.0: unified card interaction/state model for slash commands, approvals, options, and notices.

## Implementation Steps

1. Add `system.notice` to event schema and runtime event support.
2. Extend `CardSession` and `CardTimeline` to store session-scoped notices and independent notice cards.
3. Extend rendering so notice entries are visually distinct and compact in the timeline.
4. Extend the Feishu adapter wrapper in `hook_runtime.py`:
   - classify known Hermes system notices from `send`;
   - classify heartbeat updates from `edit_message`;
   - try current-session card update first;
   - retry as independent notice card if the current session is already completed or missing;
   - fallback to original native send/edit on sidecar failure.
5. Add tests before production changes:
   - schema acceptance;
   - timeline rendering;
   - server independent-card creation;
   - adapter send/edit interception and fallback.
6. Install locally into the Hermes runtime and smoke test in the Lark `奥妹` chat.

## Acceptance

- Targeted pytest passes.
- Existing slash-command cards (`/new`, `/model`) keep working.
- Grey native notices are reduced for the covered classes.
- No push/release until Bailey verifies the local behavior.
