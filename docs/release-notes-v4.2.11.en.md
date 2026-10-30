# Hermes Feishu Streaming Card V4.2.11

[中文](release-notes-v4.2.11.md) | [English](release-notes-v4.2.11.en.md)

V4.2.11 fixes Issue #202. After `interaction.requested` sent and promoted a replacement interaction card, the superseded streaming card never reached a final presentation and could retain a “using clarify” or running-tool header forever. Every superseded card is now frozen as a read-only history snapshot, while only the newest interaction card receives choices and later answer updates.

## Fixes

- **Interaction handoff snapshot**: after replacement delivery succeeds, the predecessor uses a green completed template and shows “moved to the interaction card” in both the subtitle and quote summary.
- **Visible content is preserved**: the snapshot retains the pre-request answer, thinking, timeline, tool history, attachments, and any completed prior interaction result while clearing transient tool preview and runtime phase text.
- **Controls are frozen**: repeated clarify/approval rounds no longer leave pending buttons, interaction ids, or callback tokens on predecessor cards. Only the newest card remains interactive.
- **Deterministic ordering**: the predecessor animation task is cancelled and awaited before the final PATCH, so a delayed animation frame cannot overwrite the snapshot.
- **Session styling stays scoped**: detached snapshots use the canonical session key for the original per-session title, status, and text-size configuration, including `turn_id` and topic/reply sessions.

## Failure and safety boundary

- The replacement is still sent first. Send failure restores the pre-request `CardSession`; the old message id and animation remain authoritative and the same event stays retryable.
- The predecessor PATCH uses the existing bounded update retries, `feishu_update_*` metrics, and redacted `last_update_error`. Exhausting every PATCH attempt does not revoke the delivered interaction or turn the event into a failure.
- Callback-token checks, exact chat/operator binding, absolute expiry, sequence idempotence, topic/reply routing, and native gray-text suppression are unchanged.
- This release does not modify `legacy/`, hand-edit Hermes `gateway/run.py`, or expand patcher ownership.

## Upgrade

macOS / Linux:

```bash
export HFC_VERSION=v4.2.11
bash install.sh
```

Docker:

```bash
export HFC_VERSION=v4.2.11
bash install-docker.sh
```

Windows PowerShell:

```powershell
$env:HFC_VERSION = "v4.2.11"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.11/install.ps1" | iex
```

After upgrading:

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## Verification boundary

- Issue #202 RED/GREEN regressions cover predecessor header/summary state, content and tool preservation, control removal, repeated interactions, fail-open PATCH behavior, animation ordering, and `turn_id` card configuration.
- Session/render/server/clarify focused matrix: `450 passed`.
- Full pytest in the isolated v4.2.11 candidate: `2478 passed, 6 skipped`; `git diff --check` passed.
- Local sdist/wheel builds passed. A fresh venv installed the candidate wheel, reported package/distribution `4.2.11`, imported from that venv's `site-packages`, and exited successfully for CLI help.
- Exact merge-SHA verification, post-tag Release assets, and public `site-packages` installation evidence are added to the Release and readiness records after the publication flow completes.

Expected Release assets:

- `hermes-feishu-card-v4.2.11-macos.tar.gz`
- `hermes-feishu-card-v4.2.11-linux.tar.gz`
- `hermes-feishu-card-v4.2.11-windows.zip`
- `hermes-feishu-card-v4.2.11-checksums.txt`
