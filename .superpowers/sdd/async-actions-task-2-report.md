# Async Operations Task 2 Report

## Status

DONE

## Scope Delivered

- Operations callbacks now render from the stored `DiagnosticReport` snapshot and return before fresh diagnosis, recovery execution, or Gateway restart work begins.
- `recheck`, `confirm_repair`, and `confirm_restart` schedule tracked work only from `_AfterEofJsonResponse`; repeated clicks retain exactly-once behavior.
- Background recheck/repair/restart work uses the bounded executor path with a 12.0-second diagnostic timeout and PATCHes only the delivery owned by the completing operation.
- Repair and restart finish helpers atomically complete their original inflight record before creating a successor, preventing late workers from reclaiming delivery ownership or consuming inflight capacity.
- Failure cards retain `重新检测`; failed PATCH attempts are recorded with a safe diagnostic and operation result marker.

## RED Evidence

- `test_confirm_repair_returns_executing_card_before_fresh_evidence_and_runs_once` initially failed after adding the assertion that completed work leaves no `executing` record. This exposed the predecessor lifecycle leak; the finish helpers now call `store.complete` before successor creation.
- `test_operations_patch_failure_is_recorded_on_the_completed_card` initially failed because the assertion expected the raw fake-client error. The runtime correctly uses the existing sanitized error formatter; the test now verifies the sanitized diagnostic record instead.

## GREEN Evidence

- Each newly added core test was run alone and completed within 0.11-0.33 seconds; the restart regression completed in 0.47 seconds.
- `python -m pytest tests/integration/test_server.py -q -x`: 131 passed in 11.23 seconds.
- `python -m pytest tests/integration/test_server.py tests/unit/test_operations.py -q`: 185 passed in 11.56 seconds.
- `git diff --check`: passed.

## Commits

- `4b54f8b feat: complete operations actions in background` - Task 2 implementation and integration coverage.

## Concerns

- Cancelling an asyncio diagnostic task cannot forcibly stop a synchronous report-builder thread that is already executing. The callback and operation state remain bounded by the 12-second coroutine timeout, cleanup cancels tracked tasks/futures, and the test fixtures explicitly release their blocked builders. A genuinely uninterruptible third-party report builder could still occupy an executor worker until it returns.
- No real Feishu smoke run was performed in this task; coverage is HTTP integration plus fake-client PATCH behavior.

## Reliability Follow-up

### Status

DONE

### Scope Delivered

- A successful repair now runs a second bounded `post_repair` diagnosis and creates its completed successor from that post-mutation report. If that diagnosis is unavailable, the card remains truthfully repaired, uses a visible recheckable fallback report, and sets `restart_available` to `false`.
- Repair and restart now both require the fresh diagnostic fingerprint and recovery fingerprint to match the claimed operation before any mutation can begin.
- Completion successors are linked from their predecessors in `OperationStore`, including under record-capacity pressure. Delayed callbacks authenticated with an old confirmation or recheck token resolve to the current successor card without moving delivery ownership backward.
- `preparing`, `executing`, and `restarting` cards retain a `重新检测` fallback. During the in-flight operation it returns the current progress card; after completion the predecessor link resolves to the current successor. This path is covered with all Feishu PATCH attempts failing.
- Removed the unreachable legacy synchronous repair/restart helpers and migrated their timeout and shutdown coverage to `_run_operations_restart` / `_schedule_operations_restart`.

### RED Evidence

- The three in-flight card states initially rendered no recheck button, and their callback path returned `ok: false` after PATCH failure.
- Fresh reports with a changed diagnostic fingerprint but unchanged recovery fingerprint initially still invoked recovery and Gateway restart mutations.
- A successful repair initially called only `confirm_repair` diagnosis and built its successor from the pre-mutation report.
- The store initially had no completion-successor creation or current-successor lookup API; the new capacity test failed with a missing method.

### GREEN Evidence

- Added targeted unit and integration coverage for the three in-flight fallback states, all-PATCH-failed callback recovery, delayed old confirmation delivery ownership, both fingerprint mismatch paths, post-repair diagnosis success/fallback, and the migrated restart timeout/shutdown paths.
- `.venv/bin/python -m pytest tests/integration/test_server.py -q -x`: 139 passed in 10.40s.
- `.venv/bin/python -m pytest tests/unit/test_operations.py -q`: 58 passed in 0.08s.
- `git diff --check`: passed.

### Concerns

- The bounded diagnostic timeout still cannot interrupt a synchronous report-builder thread already running in its executor; tests release all blocked fixtures in `finally`, and the task/future lifecycle remains bounded from the callback perspective.
- No real Feishu smoke test was run for this follow-up; coverage is fake-client HTTP integration plus unit state-store behavior.

## Second Re-review Fixes

### Status

DONE

### Scope Delivered

- Recheck now leaves the callback-visible `preparing` record unchanged. Its old report, fingerprints, and token remain valid while the worker creates a linked diagnosed or failed completion successor with the fresh report and transfers delivery before publishing.
- Repeated recheck fallback from the in-progress card is idempotent, including a same-fingerprint diagnosis while a controlled PATCH is delayed or fails. The old preparing token resolves the linked completion successor after that PATCH failure without scheduling another worker.
- Operations delivery records now carry a generation. The publisher checks current ownership before and after every PATCH attempt/result; a stale publisher does not add its own delivery error and performs one bounded republish of the current successor after its old write finishes.
- A normally returned synthetic `operations_diagnosis_failed` report is treated as unavailable after repair. The repaired card truthfully says recheck is unavailable and does not offer restart.

### RED Evidence

- `test_recheck_preparing_record_keeps_snapshot_until_completion_successor` first failed because `begin_recheck` rejected the callback-visible `preparing` recheck as an invalid transition.
- `test_same_fingerprint_slow_recheck_patch_keeps_one_worker_and_links_old_token` first failed because the slow same-fingerprint fallback started a second recheck worker.

### GREEN Evidence

- Added controlled delayed-PATCH coverage for old preparing-token lookup, same-fingerprint fallback idempotency, and all-attempt PATCH failure.
- Added controlled two-publisher ordering coverage proving the final emitted card belongs to the newest delivery owner.
- Added post-repair coverage where `_build_operations_report_sync` swallows an internal exception and returns the synthetic failure report normally.
- `.venv/bin/python -m pytest tests/integration/test_server.py -q -x`: 142 passed in 9.27s.
- `.venv/bin/python -m pytest tests/unit -q -x`: 824 passed, 3 skipped in 7.65s.

### Remaining Boundary

- No real Feishu/Lark smoke test was run; the new behavior is covered through HTTP integration and controlled fake-client PATCH ordering.
