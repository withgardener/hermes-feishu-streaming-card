# Hermes Feishu Streaming Card V4.2.12

[中文](release-notes-v4.2.12.md) | [English](release-notes-v4.2.12.en.md)

V4.2.12 integrates @Cassius0924's PR #206 and PR #205. Approval cards now expose only the authorization scopes Hermes allows and the sidecar rejects undeclared input. Zero-tool cards keep one stable collapsed timeline whenever reasoning display is enabled instead of changing structure between running and terminal states.

## Approval capabilities and validation

- **Capability-derived choices**: `smart_denied` exposes once/deny only; `allow_session=false` hides session/always; `allow_permanent=false` hides only always.
- **Explicit input contract**: `interaction.requested.data.allow_custom_input` flows through the hook, event, session, renderer, and callback. Approval defaults to `false`, while clarify explicitly sends `true`.
- **Server-side anti-forgery**: fixed-choice interactions accept only values declared by the current card. Forged button values, approval custom forms, and non-boolean truthy capabilities are rejected while the interaction remains pending.
- **Clarify compatibility**: single-select, multi-select, and custom “Other” answers remain available. For older events without the field, only `kind=clarify` enables custom input.

## Stable zero-tool timeline

- With the reasoning timeline enabled, zero-tool cards keep the “Reasoning and Tools · 0 tool calls” collapsed entry during loading, running, completed, and failed states.
- Initial loading shows “waiting for tool events”; later empty states explain that no reasoning or tool record is available.
- Raw `thinking.delta` stays hidden. `show_reasoning=false` retains the plain tool summary and does not force a collapsed timeline.

## Safety and scope

- Callback tokens, exact chat/operator binding, absolute expiry, interaction idempotency, topic/reply routing, and native gray-text suppression are unchanged.
- This release does not modify archived `legacy/`, hand-edit Hermes `gateway/run.py`, or expand patcher ownership.
- This cycle sends no additional real Feishu test message. PR #205's real-Feishu result is contributor evidence; PR #206 and the combined result rely on automation, independent adversarial tests, and multi-platform CI and are not represented as a maintainer client smoke.

## Upgrade

macOS / Linux:

```bash
export HFC_VERSION=v4.2.12
bash install.sh
```

Docker:

```bash
export HFC_VERSION=v4.2.12
bash install-docker.sh
```

Windows PowerShell:

```powershell
$env:HFC_VERSION = "v4.2.12"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.12/install.ps1" | iex
```

After upgrading:

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## Verification boundary

- GitHub multi-platform CI passed after PR #206 and PR #205 were updated onto the same main. The merged runtime baseline full suite reported `2481 passed, 6 skipped`.
- V4.2.12 candidate results: docs/package `94 passed`, focused matrix `830 passed`, and full pytest `2481 passed, 6 skipped`; sdist/wheel, isolated `site-packages` provenance, CLI help, and `git diff --check` all passed.
- Exact merge SHA, annotated tag, Release assets, checksums, and public-tag installation are verified during the publication flow.

Expected Release assets:

- `hermes-feishu-card-v4.2.12-macos.tar.gz`
- `hermes-feishu-card-v4.2.12-linux.tar.gz`
- `hermes-feishu-card-v4.2.12-windows.zip`
- `hermes-feishu-card-v4.2.12-checksums.txt`
