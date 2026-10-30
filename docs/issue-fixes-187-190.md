# Issues #187–#190 fixes

Date: 2026-08-04

These compatibility, maintenance, and card UX fixes are published in V4.2.6.

## Issue #189 / PR #190: Hermes Agent 0.20

Hermes Agent 0.20 moves synchronous delivery-ledger writes behind awaited `asyncio.to_thread(...)` calls. Exact Base detection now accepts only that awaited wrapper at the existing verified ledger anchors. Unknown wrappers, missing `await`, reordered ledger operations, and inexact final-send anchors remain fail-closed.

The regression matrix covers patch application/removal, installer detection, install/restore, an unawaited-wrapper rejection, and a byte-identical round trip against the official 0.20 `gateway/platforms/base.py` source.

## Issue #188: short validation result replaces the answer

Completion reconciliation now preserves a substantial streamed answer when the terminal completion is only a much shorter postscript. The two blocks remain visible in the main answer area, separated by a divider. The rule is content-agnostic and does not parse private validator names or status markers; a normal completed answer still replaces a short progress preface.

## Issue #187: repeated choices stay above later messages

When an active session receives `interaction.requested`, the sidecar sends a fresh complete current-state card and promotes its Feishu message id as the target for later updates. Each new choice therefore appears at the latest chat position, while prior cards remain historical snapshots.

The new delivery uses an interaction-specific idempotency key. If sending the promoted card fails, the session is restored to its exact pre-request state so Hermes can retry safely. Existing callback token and chat checks remain unchanged.

## Local `/update`: normal venv symlinks rejected

The update preflight previously rejected a standard venv `bin/python` symlink, so a healthy Hermes install was reported as `hermes_runtime_unavailable`. The independent maintenance runner also resolved its own venv Python symlink to the backing interpreter, losing the venv `site-packages` and failing at `sidecar_stop_failed`.

Runtime binding and import-origin verification now preserve the lexical venv path while still using only the fixed Hermes and maintenance runtime candidates. Regression tests cover both the Hermes command binding and the full maintenance state machine with POSIX venv symlinks.

The read-only native update check and target fetch retain fail-closed timeouts,
but now allow up to five minutes each so a successful slow Git fetch is not
misclassified as unavailable after only 60 seconds.

Hermes 0.20 no longer carries the legacy root `VERSION` file. Detection now
reads the literal `hermes_cli.__version__` assignment without importing Hermes
before falling back to the nearest Git tag, so doctor and the final update card
report `0.20.0` instead of a stale calendar tag such as `v2026.7.30`.

## Verification

- Focused patcher, detection, installer, session, and completion reconciliation tests.
- Complete server integration tests, including repeated interaction promotion and rollback after send failure.
- Real local `/update` preflight and confirmation-card checks against a symlink-based Hermes venv.
- Full repository test suite and `git diff --check` before publishing V4.2.6.
