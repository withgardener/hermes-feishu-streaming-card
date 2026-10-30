# V4.1.3 Release Notes

[English](release-notes-v4.1.3.en.md) | [中文](release-notes-v4.1.3.md)

V4.1.3 combines three upgrade-compatibility fixes: integrity fence-binding convergence from Issue #158, same-name answer-delta callback selection contributed by @dake6767 in PR #168, and the tool/streaming/interaction hook loss after Hermes' `TurnRunner` refactor reported in Issue #169. The goal is to keep official upgrade, diagnosis, and uninstall flows verifiable and reversible without weakening fail-closed safety.

## Fix

- `integrity acknowledge-review` can atomically migrate a plan binding for the same Hermes target only after two current recovery/integrity-plan checks report installed, two checks confirm no sidecar health and no pidfile, explicit `--yes`, an exact old/current `target_identity` match, and an unchanged fence snapshot CAS.
- A different target identity, state drift, a running sidecar, an unknown legacy fence, or a dirty/unverifiable plan still fails closed. This is not a force-clear mechanism.
- When an independent restart fence has a non-empty `pre_repair_runtime_hash`, acknowledgement clears manual review and updates the plan binding while preserving restart/hash until a different runtime id sends a generation/package-matching `runtime.hello`.
- `doctor --explain` prints the complete `integrity migrate-safe` command for `integrity_migration_required`. Other manual-review cases first require installed-evidence review and then print a complete `integrity acknowledge-review` command with explicit config, Hermes, and state paths.
- When Hermes defines same-name `_stream_delta_cb` functions for native text streaming and a streaming-TTS fallback, the answer-delta hook selects only the callback that calls `_stream_consumer.on_delta`; upgrades relocate an older misplaced managed hook.
- Hermes commit `1a3a9de`'s `TurnRunner` seam is supported: stable tool, answer, thinking, clarify, approval, and status hooks use verified `TurnContext` fields, and the status hook runs only after `ctx = self._ctx` is bound.
- Doctor now derives callback capabilities from actual patcher output. A named TurnRunner callback whose structure is not safely patchable produces an explicit `not safely patchable` refusal instead of a false partial/supported result; legacy Hermes and corrupt-marker recovery remain available.

## Upgrade and Recovery

Keep using the official installer and diagnostics. Do not edit `runtime-integrity-fence.json` or call internal Python functions:

```bash
export HFC_VERSION=v4.1.3
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain
hermes-feishu-card setup --config CONFIG --hermes-dir HERMES_DIR --yes
```

If a real Hermes update removes the hook, rerun official `install` as directed by doctor. When install state is verified as installed but readiness remains `manual_review_required`, stop the sidecar, run the displayed `integrity acknowledge-review --config CONFIG --hermes-dir HERMES_DIR --state-dir STATE_DIR --yes`, start the sidecar, and manually restart Hermes Gateway once. Finally verify `readiness: ready`, `readiness.reason: runtime_ready`, and `hook.status: installed`.

## Candidate Acceptance Scope

- Automated coverage includes successful same-target plan transition, default refusal, different-target refusal, double current-plan/state/process checks, CAS protection, and restart/hash preservation.
- Diagnostics cover complete migration and manual-review commands without exposing real paths, fingerprints, or private state evidence.
- The source regression against Hermes `1a3a9de630a809cf1b177ec0ddf5b7ff66291e65` must produce 14 managed hook blocks, one of each of the six moved TurnRunner hooks, idempotent repeat patching, byte-for-byte `remove_patch`, and `supported/full` doctor detection.
- Before release, the Issue #158 reporter still needs to retest the candidate on Ubuntu 24.04 after a real Hermes upstream update through the official flow. The Issue #169 reporter needs to use the same candidate on latest Hermes and confirm full doctor compatibility, restored tool/streaming output, and no duplicate native gray text. Manual edits to Hermes `gateway/run.py` or the fence do not count.
- Exact merge SHA, public tag/install, and Release assets remain release-stage gates.
