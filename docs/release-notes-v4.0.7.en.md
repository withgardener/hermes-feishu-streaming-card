# V4.0.7

V4.0.7 decouples the Linux/systemd sidecar lifecycle from Hermes Gateway and includes PR #124's self-improvement notice-card fix. Restarting the Gateway no longer terminates the sidecar with the same cgroup, and the upgrade script prefers the Hermes runtime venv instead of splitting package state across system and runtime Python installations.

## Linux/systemd sidecar lifecycle

- Issue #125: when a systemd user manager is available, `setup` and `start` launch the sidecar as an independent transient user service.
- The unit uses `Type=exec`, `Restart=on-failure`, and a short restart delay. It is owned by the user service manager rather than the `hermes-gateway` cgroup.
- A sidecar created by the previous detached-process path is migrated only when PID, process token, and `/health` identity all match. Unknown processes remain fail-closed.
- If systemd restarts the process with a new PID, `status` and `stop` still use the stable process token and recorded unit identity.
- macOS, Windows, containers, and Linux environments without a working systemd user manager retain the detached-process fallback.

## Python install path

- `install.sh` checks the Hermes `venv` and `.venv` interpreters before falling back to `PYTHON` or `python3`.
- `HFC_PYTHON` is the explicit interpreter override.
- The Debian/Ubuntu externally-managed fallback remains available, but a normal Hermes venv is no longer bypassed in favor of system Python.

## Self-improvement notice cards

- PR #124 prevents a session-scoped self-improvement notice from creating a new primary card after its original session is gone.
- After the server returns `applied: false`, the existing runtime retries the notice as an independent card with its own completed lifecycle.
- The next conversation creates and updates its own card instead of overwriting a stale self-improvement card.

## Credits

- Thanks to @nasvip for issue #125's systemd cgroup, PID, Python-environment, and post-recovery health evidence.
- Thanks to @hzy for PR #124's self-improvement notice lifecycle fix and regression coverage.

## Validation

- Automated regressions cover the systemd lifecycle, safe migration of an owned legacy process, PID changes after restart, safe stop behavior, and Hermes venv Python selection.
- PR #124 full suite: `1317 passed, 3 skipped`; `git diff --check` passed.
- V4.0.7 full release gate: `1324 passed, 3 skipped`; `git diff --check` passed.
- The sdist and wheel built successfully; a clean Python 3.12 venv imported version `4.0.7` from the wheel.
- Public tag/Release assets and one-line install verification will be recorded after publishing the Release.

## Release assets

- `hermes-feishu-card-v4.0.7-macos.tar.gz`
- `hermes-feishu-card-v4.0.7-linux.tar.gz`
- `hermes-feishu-card-v4.0.7-windows.zip`
- `hermes-feishu-card-v4.0.7-checksums.txt`
