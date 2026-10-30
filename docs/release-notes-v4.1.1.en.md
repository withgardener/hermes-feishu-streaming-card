# V4.1.1 Release Notes

[English](release-notes-v4.1.1.en.md) | [中文](release-notes-v4.1.1.md)

V4.1.1 is an upgrade-recovery safety hotfix for V4.1.0. It does not change the per-chat native policy, table compaction, or native handoff product behavior. It tightens first-heartbeat handling, operator review fences, legacy sidecar migration, and setup interpreter consistency.

## Fixes

- When the verified Hermes on-disk plan is already `installed` but the sidecar has not received its first `runtime.hello` / `runtime.heartbeat`, readiness remains `runtime_heartbeat_waiting` / `runtime_heartbeat_missing`; this waiting state does not persist a restart/manual-review fence.
- Added `integrity acknowledge-review`. It verifies the Hermes plan, sidecar health, and pidfile twice and requires a target-bound fence, cross-process lock, and unchanged CAS snapshot. Any failed precondition is fail-closed.
- An unbound V4.1.0 fence can migrate only in the exact `restart=true + manual=true + empty pre_repair_runtime_hash` shape. An unbound non-empty hash remains refused; a bound non-empty hash clears only the manual-review bit and retains the Gateway restart fence until a different runtime id sends a matching generation/package `runtime.hello`.
- A legacy `0644` pidfile is a migration candidate only inside a current-user-owned, non-symlink, private `0700` state directory, and it is tightened to `0600` through an already-open fd identity binding. Directory, inode, record-shape, process, or health identity drift refuses migration.
- A running pidfile-less sidecar is never silently adopted or killed. A detached child must first observe the exact PID + process-token manager record written by its parent before reading configuration or listening; if that write fails, the child exits itself. Managed sidecars stop only through a loopback, process-token-authenticated self-shutdown request; HFC no longer sends TERM/KILL to a numeric PID/PGID. Unsupported legacy processes and shutdown timeouts keep the process and pidfile for manual handling.
- `setup/install` rechecks the Hermes runtime venv with isolated `python -I`, requires the package to come from that venv's `site-packages`, and then compares `/health` package/Python identity before a managed restart. Plain `start` also requires an isolated matching import and passes the verified canonical Hermes root explicitly to the runner, so conflicting environment variables cannot retarget it; `start/status/stop` share an explicit `--env-file`.
- When a specific non-loopback address is explicitly enabled, the authenticated event listener is paired with a same-family loopback management listener for local health and process-token shutdown. Wildcard listeners are not bound a second time.

## Safe Recovery Order

```bash
# 1. Verify Hermes and integrity state; never edit gateway/run.py manually
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain

# 2. Stop the old sidecar and verify health is unreachable and no pidfile remains
hermes-feishu-card stop --config CONFIG

# 3. Use only when doctor shows installed and runtime cannot self-clear review
hermes-feishu-card integrity acknowledge-review \
  --config CONFIG \
  --hermes-dir HERMES_DIR \
  --state-dir STATE_DIR \
  --yes

# 4. Rerun official setup, then manually restart sidecar and Hermes Gateway
hermes-feishu-card setup --config CONFIG --hermes-dir HERMES_DIR --yes
```

`acknowledge-review` is not a force-clear switch. Dirty targets, unknown backups/manifests, a non-private fence, a reachable sidecar, or any pidfile require operator resolution first. After acknowledgement, manually restart sidecar and Hermes Gateway and require a new `runtime.hello` before considering readiness restored.

## Install

```bash
export HFC_VERSION=v4.1.1
bash <(curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh)
```

The Docker Compose example defaults to `v4.1.1`. Back up local configuration and `.env` before upgrading. Never publish Feishu secrets, real chat ids, pid tokens, runtime ids, or recovery fingerprints.

## Release Acceptance Status

Candidate `20b7b06` completed these gates:

- full pytest: `2194 passed, 4 skipped`; `git diff --check` passed;
- wheel/sdist build and isolated `site-packages` import/version provenance passed;
- real-process tests from the installed wheel: `8 passed`; independent review found no P0-P2 issue.

The following post-candidate / post-tag gates remain part of the release workflow and are not pre-declared as passed:

- Python 3.9 / 3.12 CI and exact-merge-SHA regression;
- public tagged installation and Release assets;
- all four Linux managers and the ordinary non-privileged Docker topology;
- local and remote upgrade/restart plus real Hermes-model and real Feishu card/native/card smoke;
- heartbeat waiting without a fence, empty/non-empty hash acknowledgement branches, legacy `0644`, and pidfile-less refusal paths.
