# Hermes Feishu Streaming Card V4.2.3

Release date: 2026-08-01

V4.2.3 fixes the WebSocket callback evidence-forwarding gap found during real Feishu acceptance of V4.2.2. After a user clicked an `/update` confirmation card, the native action reached the Gateway, but the hook omitted `update_evidence_fingerprint` when constructing the sidecar payload. The sidecar therefore failed closed as designed, leaving the original confirmation card unchanged.

## Fix

- The WebSocket hook now reads `update_evidence_fingerprint` from the card value and forwards it unchanged to the sidecar.
- A new executor-facing unit regression directly asserts that the hook-to-sidecar payload preserves this field; it failed on the missing field before the fix and passes afterward.
- The native action still returns its fast empty acknowledgement first. Card PATCH work and later maintenance scheduling remain asynchronous.

## Unchanged safety boundaries

- The sidecar continues to validate initiator, chat, profile, operation token, target evidence, evidence fingerprint, and expiry. Missing or mismatched evidence remains fail-closed.
- Cancel must reach a terminal state and never start the updater. Confirm must attempt to publish locking/preparation before scheduling independent maintenance.
- Only an exact bare `/update` in a Feishu private chat uses the maintenance card. Group, non-Feishu, alias, and parameterized commands retain Hermes' original behavior.
- Installation and recovery continue through the official patcher/setup/install flow. Do not edit `gateway/run.py` by hand.

## Verification

- The related hook/runtime/server/Feishu SDK matrix passed: `670 passed, 1 skipped`.
- Full pytest passed: `2309 passed, 5 skipped`. `git diff --check`, sdist/wheel, and clean Python 3.12 `site-packages` package/distribution/CLI provenance also passed. PR CI and exact-merge-SHA testing continue in the release gate.
- Candidate acceptance created a fresh private-chat `/update` card and clicked Cancel: the sidecar update succeeded, the original card reached “cancelled / Hermes update not executed”, Hermes Git HEAD and `update.log` were unchanged, and no updater process existed. Repeat the same acceptance after installing the public tag.

## Install

```bash
export HFC_VERSION=v4.2.3
bash install.sh
```

After upgrading an existing installation, rerun the official `setup` / `install` flow so the Hermes runtime venv, managed hook, sidecar, and independent maintenance runtime all use V4.2.3.

## Release assets

- `hermes-feishu-card-v4.2.3-macos.tar.gz`
- `hermes-feishu-card-v4.2.3-linux.tar.gz`
- `hermes-feishu-card-v4.2.3-windows.zip`
- `hermes-feishu-card-v4.2.3-checksums.txt`

Verify downloaded files against `hermes-feishu-card-v4.2.3-checksums.txt`.
