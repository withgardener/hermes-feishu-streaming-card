# V4.1.4 Release Notes

[English](release-notes-v4.1.4.en.md) | [中文](release-notes-v4.1.4.md)

V4.1.4 fixes the Windows legacy-install migration gap reported in Issue #171. When an older owned hook and its backup remain but `.hermes_feishu_card_manifest` is missing, official `install` / `setup` can rebuild the manifest after strict verification and upgrade the hook.

## Fix

- With a missing manifest and an existing Gateway backup, the installer accepts a legacy owned hook only when `remove_patch_lenient(current) == backup`, the backup is parseable clean source, and neither target is a symlink.
- Optional Cron and required exact Base use their strict patch-removal checks; each current file must restore byte-for-byte to its backup. If the legacy release had no Base hook, the installer creates the Base backup, applies the current hook, and writes `manifest_version: 2` according to current Hermes detection.
- Migration uses the install flow's Windows portable write sequence instead of the directory-fd recovery transaction that is intentionally unavailable on Windows. Existing targets are read, verified, written, flushed, and reverified while an exclusive handle is held; owned rollback is also fenced by identity-and-digest snapshots. If newly created evidence cannot be deleted safely after a failure, it is preserved for manual review.
- `--no-repair` continues to disable automatic repair. User edits outside owned markers, post-validation concurrent edits, mismatched backups, missing targets, symlinks, and unparseable source still fail closed and are never overwritten automatically.

## Root Cause

The public v4.0.14 CLI does create a manifest; a missing manifest in Issue #171 means the local ownership evidence became incomplete. Reproduction also showed that Unicode comments, CRLF, and native Windows relative paths do not by themselves break `ast.parse`, text hashes, or path comparison. The real blocker was that v4.1.3 classified an older generated owned-block body as corrupt markers while the general recovery transaction is unavailable on Windows by design.

Do not hand-create a manifest or call internal `apply_patch()` APIs. V4.1.4 derives migration only from the existing source and backup evidence.

## Upgrade and Retest

```bash
export HFC_VERSION=v4.1.4
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain
hermes-feishu-card install --hermes-dir HERMES_DIR --yes
```

On Windows PowerShell, use the official `install.ps1` / `setup` flow and select `v4.1.4`. Success prints `manifest: rebuilt` and `install ok`; restart Hermes Gateway, then verify that doctor reports install state `installed`.

Repository automation covers the no-directory-fd Windows-equivalent branch, the Windows exclusive handle, `--no-repair`, missing Cron/Base targets, edits outside owned blocks, and concurrent edits before write/rollback. Separate isolated fixtures created by the public v4.0.14 `site-packages` cover a regular Gateway, Hermes v0.19.0 required exact Base, optional Cron, and Unicode + CRLF. The reporter's real Windows acceptance remains pending; full pytest, CI, the exact merge SHA, wheel/sdist, isolated `site-packages` installation, and Release assets remain release gates.
