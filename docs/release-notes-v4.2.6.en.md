# Hermes Feishu Streaming Card V4.2.6

Release date: 2026-08-04

V4.2.6 resolves Issues #187, #188, #189 and PR #190, fixes bare Feishu `/update` on standard venv symlink layouts, and reports Hermes 0.20 package versions accurately.

## Fixes

- **Issue #187 — repeated choice-card position**: every `interaction.requested` on an active session creates a complete new choice card and promotes its message id as the target for later updates. Older cards stay as history; a failed create restores the exact pre-request state so Hermes can retry safely.
- **Issue #188 — short terminal postscript replacing the answer**: when streaming already produced a substantial answer and completion adds only a much shorter validation or closing postscript, both blocks remain in the main answer area with a divider. An ordinary complete terminal answer still replaces a short progress preface.
- **Issue #189 / PR #190 — Hermes Agent 0.20**: exact Base detection accepts `await asyncio.to_thread(...)` only at the verified delivery-ledger anchors. Missing `await`, unknown wrappers, reordered writes, or inexact anchors remain fail-closed; install/remove stays byte-identical.
- **Bare Feishu `/update`**: runtime binding and the independent maintenance process preserve the lexical venv `bin/python` symlink, retaining the correct `site-packages`. Read-only update checks and target fetches keep fail-closed timeouts but allow up to five minutes for a successful slow Git fetch.
- **Hermes 0.20 version reporting**: when the root `VERSION` file is absent, detection statically reads a literal `hermes_cli.__version__` assignment before falling back to Git. Doctor and update cards therefore report `0.20.0` instead of a stale calendar tag.

## Safety boundaries

- Version detection never imports Hermes and rejects dynamic, concatenated, or otherwise non-literal expressions.
- Unknown Hermes source shapes still reject patching; unknown or unsupported event paths remain fail-open.
- Existing `/update` initiator, chat, profile, target-evidence, drain, snapshot, and recovery verification boundaries are unchanged.
- The tag is created only after a clean detached worktree verifies the exact main merge SHA.

## Install

```bash
export HFC_VERSION=v4.2.6
bash install.sh
```

After installation:

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card maintenance status
```

## Release assets

- `hermes-feishu-card-v4.2.6-macos.tar.gz`
- `hermes-feishu-card-v4.2.6-linux.tar.gz`
- `hermes-feishu-card-v4.2.6-windows.zip`
- `hermes-feishu-card-v4.2.6-checksums.txt`

Verify each download against the SHA-256 checksums file.
