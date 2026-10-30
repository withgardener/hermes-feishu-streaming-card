# Hermes Feishu Streaming Card V4.4.0

[中文](release-notes-v4.4.0.md) | [English](release-notes-v4.4.0.en.md)

V4.4.0 is a feature and experience release designed around current Hermes. Feishu `/commands` moves from paginated text to a live native capability center, common Hermes commands gain category navigation, safe quick actions, and KPI visualization, and stream-backlog diagnostics plus extreme-Markdown fallbacks become more accurate.

## Current Hermes Baseline

- Released compatibility baseline: Hermes Agent `v2026.8.27` / `0.20.6`.
- Forward validation: Hermes `main@4f22543509d1b91dc45bcb369447126c5eb14fb7` (2026-08-30).
- Reads the current `hermes_cli.commands.COMMAND_REGISTRY`, including categories, aliases, argument hints, subcommands, argument modes, busy policies, and gateway availability.
- Automatically recognizes newer `/bg`, `/btw`, `/plan`, gateway `/busy`, and runtime plugin/skill commands without copying a fixed HFC allowlist.

## Native Hermes Capability Center

- The `/commands` card provides overview, category, and command-detail views.
- The overview reports the live Hermes core-command count and offers quick access to status, context, usage, tasks, sessions, and model selection.
- Category pages show complete usage and descriptions. Detail pages expose aliases, subcommands, argument mode, busy policy, and command source.
- A registry, plugin, or skill discovery failure remains fail-open and preserves the original `/commands` text response.

## Safe Command Interaction

- `/status`, `/context`, `/usage`, `/agents`, `/sessions`, `/profile`, `/version`, and the existing native `/model` and `/resume` pickers can be launched from the card.
- A quick action copies the original `MessageEvent` and re-enters the Feishu adapter. Hermes access control, busy policy, plugin hooks, session ownership, and original handlers stay authoritative.
- Group callbacks are bound to the initiating operator and still pass Hermes group admission.
- State-changing commands such as `/update`, `/new`, `/stop`, `/undo`, `/pause`, and `/yolo` are never one-click actions. Commands needing arguments must be sent explicitly in the composer.

## Visualization and Runtime Metrics

- `/status`, `/context`, `/usage`, `/agents`, `/sessions`, `/profile`, and `/reasoning` promote stable `Label: Value` fields into KPI columns.
- The complete Hermes output remains visible below. Unknown shapes stay full-text cards instead of losing data for presentation.
- `FlushController.pending_count` and `update_queue_peak` now report the real number of updates coalesced while a PATCH is active rather than a boolean 0/1 signal.

## Markdown Reliability

- Ordinary long tables continue to split by row with repeated headers, and a single oversized cell still becomes structurally valid continuation rows.
- A header that exceeds the per-block budget is replaced with an explicit safe-fold notice.
- A row whose column framing leaves no room for any valid continuation row is safely folded instead of using character-based plain splitting.
- The five-table `compact` / `truncate` policy, 200-tagged-element limit, 28,000-byte JSON budget, and terminal native-answer handoff remain unchanged.

## Verification Status

- Focused regressions cover live-registry discovery, capability-card structure, copied-event dispatch, state-changing-command rejection, KPI full-text preservation, real backlog depth, and adversarial tables.
- The catalog was loaded against an isolated checkout of current Hermes main: 66 gateway commands were discovered, including current metadata for `/bg`, `/btw`, `/plan`, `/model`, `/busy`, and `/commands`.
- Full pytest: **`3356 passed, 5 skipped`**; `git diff --check`: **passed**.
- sdist/wheel: **built successfully**. In a clean Python 3.12 venv installed from the wheel, package and distribution versions both report `4.4.0` from isolated `site-packages`; the CLI entry point and `--help`: **passed**.
- Release PR CI, exact merge, annotated tag, public install, and Release assets/checksums are reported only after the release workflow actually completes.
- Real Feishu private/group smoke: **passed on 2026-08-31**. The `4.4.0` candidate wheel ran in an isolated CLI environment using official Hermes `v2026.8.27` / `0.20.6`. Private and group chats covered the `/commands` overview, category navigation, `/model` details, back navigation, and the safe `/status` quick action. Private `/context` covered both the empty state and a populated usage view, and ordinary private/group streaming cards completed with their footers.
- Post-acceptance sidecar state was `healthy / runtime_ready`: `events_received/events_applied=14/14`, sends `3/3`, updates `43/43`, with zero event rejections, send/update failures, or profile mismatches. The test group had one human operator, so changed-operator rejection remains automation-backed. No real chat/user/message ids, credentials, or private screenshots are retained.
