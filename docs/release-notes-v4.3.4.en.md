# Hermes Feishu Streaming Card V4.3.4

[中文](release-notes-v4.3.4.md) | [English](release-notes-v4.3.4.en.md)

V4.3.4 fixes runtime interaction listener startup/exit reliability and makes `doctor --json` use the correct V3 install contract for Hermes 0.20 Hybrid installations.

## Fixed

- PR #229: listener binding completes directly without invoking `socket.getfqdn()` reverse-DNS lookup. The `serve_forever` thread is a daemon, so a short-lived command exits even if it does not explicitly call `close()`.
- Issue #233: after detecting `manifest_version: 3`, doctor uses the V3 runtime binding, plugin entrypoint, and fixed-tag Hybrid inspector instead of invoking Legacy install diagnosis, recovery, or integrity-repair planning. A valid installation reports `installed` without Legacy manifest/hash/path/source failures.
- The hosted-macOS blocked-delivery close regression now uses a Future deadline to verify bounded completion without counting runner scheduling overhead. Production `_CLOSE_JOIN_SECONDS` is unchanged.

## Safety boundaries

- V3 phase, plugin-config, patched-target, backup, or runtime-identity drift remains fail closed with V3-specific findings. A V3 manifest never exposes Legacy automatic repair and instead directs operators to the official V3 restore/reinstall flow.
- Listener loopback/explicit-host policy, runtime interaction token authentication, callback ownership, Feishu card/API delivery semantics, Hermes patch ownership, and the archived `legacy/` runtime are unchanged.
- PR #228 is not included. Its disable-config merge precedence, cross-card-dialect update boundary, and current-main conflicts still require contributor changes.

## Verification status

- Combined #229 listener/daemon, #233 valid/tampered V3 install and doctor, diagnostics/CLI, and hosted-macOS timing regressions: **`191 passed`**.
- Full pytest in a disposable 4.3.4 venv: **`3275 passed, 6 skipped in 634.95s`**. `git diff --check`: **passed**.
- PEP 517 sdist/wheel and fresh Python 3.12 wheel-only provenance: **passed**. Package and distribution versions are `4.3.4`, import comes from isolated `site-packages`, exactly one `hermes_agent.plugins` entrypoint is present, all 24 provenance slices are packaged, and the main CLI plus `enable/disable --help` exit 0.
- Tests run `32710110323` (10 jobs) and CodeQL run `32710110375` passed for PR #234 candidate HEAD `435ea4e355719e0f2d904cf1bac986ff18f70876`, covering Ubuntu Python 3.9–3.12, macOS, Windows, the PowerShell installer, Docker Compose, Feishu SDK, and the fixed Hermes fixture.
- The exact merge/tag and Release assets/checksums continue as publication gates and are not marked passed before completion.
- This cycle changes no Feishu card or API delivery semantics, so no additional real Feishu test message is sent. It does not replace V4.3.3's outstanding first-reply thread client acceptance.
