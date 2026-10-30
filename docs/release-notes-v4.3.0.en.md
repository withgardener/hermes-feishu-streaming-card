# Hermes Feishu Streaming Card V4.3.0

[中文](release-notes-v4.3.0.md) | [English](release-notes-v4.3.0.en.md)

V4.3.0 adds a source-proven Hybrid integration for Hermes Agent `v2026.8.3` (0.20.0, pinned commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`). Verified Hermes Plugin hooks own the native lifecycle, while 17 exact patch groups supply the missing UI and delivery boundaries. The sidecar remains the only Feishu card owner; incomplete or mismatched evidence fails closed to no install instead of guessed compatibility.

## Hermes 0.20 Hybrid integration

- Adds the production `hermes_agent.plugins` entry point, real `PluginContext` registration, and a signed process-level runtime bootstrap. Hook failures remain fail-open and the plugin does not retain live Hermes objects or full answers as durable global state.
- The fixed-tag probe binds the source commit, nine full-source hashes, 24 call-site slices, runtime Python, `site-packages` origin, distribution/entrypoint metadata, and real PluginManager subprocess evidence. A version string or `VALID_HOOKS` alone is never capability evidence.
- The fixed tag uses 17 closed patch groups across `gateway/run.py`, `agent/turn_context.py`, `agent/turn_finalizer.py`, `tools/approval.py`, `tools/delegate_tool.py`, `cron/scheduler.py`, and `gateway/platforms/base.py`. Every target has an external expected matrix, compile gate, exact detect/remove, and verified-original SHA-256.
- `manifest_version: 3` binds Hermes home, lexical venv Python, resolved interpreter, purelib/platlib, the HFC entry point, official plugin-enable config preimage, seven source backups, and transaction phase. Install is idempotent; repair converges `prepared` / `plugin_enabled`; restore and uninstall recover config and all sources byte-for-byte.

## Interaction, cards, and runtime

- The sidecar `/events` endpoint now has an event-id single-flight fence, exact first-status/JSON replay, conflict rejection, non-evictable pending owners, and completed TTL/LRU. Subagents render as their own timeline rather than inflating tool count.
- Approval, clarify, and slash interactions use a separate signed loopback callback listener that wakes the original Hermes pending handle/future directly. The callback runs outside all session/message locks, and card authority moves only after success; failure, expiry, or session replacement remains pending or fails safely.
- Fixes Issue #217 duplicate approval cards and ineffective approval: Hybrid approval round-trip keeps one UI owner and binds the exact `turn_id`, `tool_call_id`, and pending handle.
- Fixes Issues #210/#211 so frozen predecessor cards show terminal statistics and consecutive clarify selections stay bound to the current interaction. PR #213 contributes retained original-question/choice context in the completed hover state.
- Fixes Issue #221 by anchoring stable tool callbacks after Hermes core's final callback assignment, preventing tool rows from remaining in running forever.
- Fixes Issue #222 and incorporates the goal of PR #223: `interaction.select` retries only bounded, classifiable transient transport failures. Canonical success, conflicts, and unknown outcomes are never resubmitted.
- PR #220 completion notifications are explicit opt-in and keep identity, profile/chat routing, and delivery outcomes constrained. PRs #218/#219 update both CodeQL actions to one reviewed version.

## Install, upgrade, and persistence

- Fixes Issue #214: Hermes `2026.8.3` no longer falls into an unsupported “healthy sidecar but cards never activate” path. The installer proves capabilities before rendering Hybrid patches.
- Fixes Issue #215: a verified Hermes upgrade can use `install --accept-hermes-upgrade --yes` to restore prior ownership and re-probe. Source, backup, manifest, or config drift still refuses automatic repair.
- Fixes the stale-pidfile recovery deadlock in Issue #212. Cross-boot records and confirmed PID reuse are cleaned safely; unknown live processes are never killed or adopted.
- Adds `hermes-feishu-card enable --config ... --hermes-dir ... --yes` and `disable`. Enable installs a real systemd user unit, requires confirmed `loginctl` linger, binds config/env/Hermes/runtime identity, and uses `Restart=on-failure`. The unit and private manifest authenticate each other by SHA-256; drift, unknown same-name units, failed stops, and incomplete ownership are not silently overwritten or deleted.

## Community issue boundary

- Issue #216 reports that Feishu sends zero `card.action.trigger` events over the long connection. HFC cannot reconstruct a user click when the platform delivers no event, and V4.3.0 does not claim to fix that platform-side failure. Follow the Feishu acceptance checklist for subscription, published app version, app identity, and raw event evidence.
- PR #203 changes only archived `legacy/` and is not included in the active runtime. V4.3.0 does not restore a dual runtime or expand `legacy/` ownership.

## Verified scope

- A separate fixed Hermes `v2026.8.3` copy passed real venv entrypoint and capability probing, render+compile for 17 groups / seven targets, byte-stable repeated install, Git-clean restore, exact config SHA-256 recovery, and ownership-evidence cleanup.
- V3 installer/restore/script gate: `340 passed, 5 skipped`; persistent-service plus existing process/CLI loopback regression: `302 passed`.
- Full pytest: `3227 passed, 6 skipped in 378.84s`. `python -m build --no-isolation` produced `hermes_feishu_streaming_card-4.3.0.tar.gz` and `hermes_feishu_streaming_card-4.3.0-py3-none-any.whl`. A fresh Python 3.12 venv installed only the wheel and verified package origin inside that venv's `site-packages`, exactly one Hermes plugin entrypoint, all 24 provenance slices, and exit 0 from the main CLI plus `enable/disable --help`.
- These results establish a local RC, not a published tag or real Feishu client acceptance.
- Exact merge SHA, remote CI, annotated tag, Release assets, checksums, and public-tag installation remain later publication steps and are not performed automatically from this branch.

## Upgrade

```bash
export HFC_VERSION=v4.3.0
bash install.sh --hermes-home ~/.hermes
```

After installation, Linux users may explicitly enable boot persistence:

```bash
loginctl enable-linger "$USER"  # explicit user/admin action when needed
hermes-feishu-card enable \
  --config ~/.hermes_feishu_card/config.yaml \
  --hermes-dir ~/.hermes/hermes-agent \
  --yes
```

Verify:

```bash
hermes-feishu-card doctor --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent
```
