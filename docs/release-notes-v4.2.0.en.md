# Hermes Feishu Streaming Card v4.2.0

## Added

- A bare `/update` in a Feishu private chat inspects Hermes, the Git worktree, HFC hooks, the update target, active work, and the pinned maintenance artifact before showing a 120-second confirmation card.
- After confirmation, an independent process outside the Hermes checkout runs the official `hermes update --yes`, reinstalls the exact current HFC version from a private cache, restores hooks, and restarts and verifies the sidecar and Gateway.
- The original card reports draining, hook restoration, Hermes update, HFC reinstall, service startup, verification, and the final result.
- Local recovery commands are available under `hermes-feishu-card maintenance provision|status|run|resume`.
- Run `hermes-feishu-card maintenance status` before using the card flow; `maintenance resume --job ...` validates and relaunches the real independent runner.

## Safety boundary

- Only an exact bare `/update` in a Feishu private chat is intercepted. Group, non-Feishu, alias, and parameterized commands keep the original Hermes behavior.
- Confirmation is bound to the initiator, chat, profile, preflight snapshot, local evidence, and a 120-second expiry. It explicitly authorizes the official updater to fetch the latest `origin/main` at execution time.
- Confirmation first persists a maintenance admission lease so the Gateway stops accepting new work. Service shutdown begins only after two newer heartbeats both prove zero active sidecar and Gateway sessions; missing v2 task-count telemetry refuses maintenance.
- Preflight explicitly fetches and displays the current `origin/main` snapshot instead of trusting a fork's `upstream/main` summary. The official updater fetches the latest `origin/main` again by design; if the remote advances after confirmation, HFC, hooks, and services are restored first and the terminal card reports target mismatch as failure rather than claiming the original snapshot succeeded or leaving the machine stopped.
- The workflow never adds `--force`, `--force-venv`, or `--no-backup`, and never performs a custom Git reset, checkout, stash, or rollback.
- Untracked files are preserved. Unrelated tracked changes, incomplete Git operations, artifact drift, or final verification failures stop the workflow.
- The independent maintenance venv installs full wheel dependencies and imports the maintenance runner. Its one-use private credential snapshot is consumed at runner startup, and terminal or orphan snapshots are pruned. Linux requires a verifiable `systemd --user` manager and refuses launch when none is available; it does not guess that a detached child escaped the Gateway cgroup.
- Gateway telemetry must prove that the aggregate count came from one `_active_work_count()` sample and that the running `HERMES_HOME` matches the checkout's drain-marker directory; secondary or custom homes without that proof refuse card-based automatic update.
- Final readiness checks a new sidecar PID, a new Gateway runtime identity, a fresh heartbeat, the HFC version, Hermes-venv Python identity, `site-packages` import origin, and the managed hook.

## Release assets

- `hermes-feishu-card-v4.2.0-macos.tar.gz`
- `hermes-feishu-card-v4.2.0-linux.tar.gz`
- `hermes-feishu-card-v4.2.0-windows.zip`
- `hermes-feishu-card-v4.2.0-checksums.txt`
