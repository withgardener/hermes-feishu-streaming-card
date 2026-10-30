# Hermes Feishu Streaming Card V4.2.5

Release date: 2026-08-02

V4.2.5 is an audit-driven safety hotfix covering quoted-turn isolation, maintenance recovery, diagnostic actions, installer version resolution, public-template consistency, and an exact tag/commit gate for Release Assets.

## Audit findings and fixes

- **HFC-REV-20260801-01**: canonical `turn_id` isolates quoted turns so a late terminal from an earlier turn cannot complete a later one; legacy producers without an explicit ID retain alias fallback.
- **HFC-REV-20260801-02**: duplicate maintenance resume is coalesced without mutating the journal, one-shot credentials, or drain fence.
- **HFC-REV-20260801-03**: every maintenance command is bound to the confirmed Hermes checkout, runtime, cwd, and environment instead of another PATH-selected Hermes install.
- **HFC-REV-20260801-04**: the first non-terminal delta of a quoted turn is no longer dropped by stale sequence deduplication state.
- **HFC-REV-20260801-05**: card/native delivery policy is pinned at the canonical turn identity for the whole turn; policy changes apply to the next turn.
- **HFC-REV-20260801-06**: maintenance resume reconciles external drain from the persisted phase before readiness; post-restore phases clear drain first.
- **HFC-REV-20260801-07**: doctor suggests `acknowledge-review` only when the recovery and integrity plans jointly prove it executable; every other manual-review reason must repair install state and rerun diagnosis.
- **HFC-REV-20260801-08**: installer `latest` on Bash, PowerShell, and Docker resolves to a stable `vX.Y.Z` tag or exits before pip/setup; it never falls back implicitly to `main`.
- **HFC-REV-20260801-09**: the public `config.yaml.example` version marker now matches package metadata.

## Release hardening

Release Assets accept only a full annotated `refs/tags/vMAJOR.MINOR.PATCH`. The workflow peels the tag to one exact commit, runs reusable cross-platform tests at that commit, and fully reverifies the tag, commit, `origin/main` ancestry, and five release markers before build and again before upload. This is a separate residual-risk control, not a tenth audited bug.

## Install

```bash
export HFC_VERSION=v4.2.5
bash install.sh
```

`latest` also resolves and pins the latest stable tag. If the Release API is unavailable, set `v4.2.5` explicitly instead of relying on an implicit `main` fallback.

## Release assets

- `hermes-feishu-card-v4.2.5-macos.tar.gz`
- `hermes-feishu-card-v4.2.5-linux.tar.gz`
- `hermes-feishu-card-v4.2.5-windows.zip`
- `hermes-feishu-card-v4.2.5-checksums.txt`

Verify downloads against the checksums file.
