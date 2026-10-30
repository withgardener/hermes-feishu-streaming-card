# Hermes Feishu Streaming Card V4.3.5

[中文](release-notes-v4.3.5.md) | [English](release-notes-v4.3.5.en.md)

V4.3.5 fixes a keyword-compatibility gap between the HFC `edit_message` wrapper and the Hermes v2026.8.3 Feishu adapter, preventing completion/streaming fallback from raising `TypeError` for unsupported internal `metadata`.

## Fixes

- PR #235: when card routing does not take ownership and the wrapper falls back to the original Feishu adapter, it inspects the original `edit_message` signature. If that method supports neither a `metadata` parameter nor `**kwargs`, the wrapper removes only the HFC-owned `metadata` keyword before calling it.
- Methods that explicitly support `metadata` or `**kwargs` continue receiving the complete keyword set, preserving forward compatibility.
- Unrelated unknown keywords are not swallowed and still raise `TypeError` from the original method, preserving fail-closed debugging behavior.

## Safety Boundaries

- This release does not change card ownership, thread placement, callback authentication, Feishu API payloads, Hermes patch ownership, or the archived `legacy/` runtime.
- If a signature cannot be inspected, only wrapper-owned `metadata` is removed; every other keyword is preserved, so ordinary programming errors cannot be disguised as successful delivery.

## Verification

- Independent direct regressions: **`4 passed`**. Hook/server hot-area suites: **`841 passed`**.
- Full pytest on the exact PR head: **`3279 passed, 6 skipped in 599.42s`**.
- Focused v4.3.5 docs/package/native-provenance gate: **`99 passed`**. Full pytest in a disposable wheel environment: **`3280 passed, 5 skipped in 555.86s`**. `git diff --check`: **passed**.
- PEP 517 sdist/wheel and fresh Python 3.12 wheel-only provenance: **passed**. Package and distribution versions are `4.3.5`, import comes from isolated `site-packages`, exactly one `hermes_agent.plugins` entrypoint is present, all 24 provenance slices are packaged, and the main CLI plus `enable/disable --help` exit 0.
- PR #235 HEAD `5b3bf428eb688df4b95607cba1a4ce50e2eeb8d0`: Tests run `32719244038` attempt 3 and CodeQL run `32719244032` **passed**. The first two attempts failed only because the fixed Hermes fixture clone received GitHub HTTP 429; the third attempt passed the fixture and every platform job.
- Exact PR merge: `d56555bf9e716de67ed14f8ed992df1ec55cea21`. The release PR, exact release merge, tag, and Release assets/checksums continue through the release workflow.

## Credits

Thanks @Lite-G for reporting, reproducing, testing, and implementing PR #235.
