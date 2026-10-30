# Hermes Feishu Streaming Card V4.3.7

[中文](release-notes-v4.3.7.md) | [English](release-notes-v4.3.7.en.md)

V4.3.7 restores installer compatibility with the Hermes 2026-08-25 core: HFC can still locate the exact Base patch contract when `BasePlatformAdapter._process_message_background` calls the media/local delivery filters with `session_key=session_key`.

## Fixes

- Issue #240 / PR #241: dedicated exact matchers for `filter_media_delivery_paths(...)` and `filter_local_delivery_paths(...)` accept both the legacy single-positional-argument call and the new call with exactly one `session_key=session_key` keyword.
- `install`, `setup`, `doctor`, and installer detection no longer classify the newer Hermes source as `exact_delivery_contract: missing_or_unsupported`; apply/remove/restore remain idempotent and byte-exact.
- The call shape was verified in real Hermes source at `82b32f32ef6a6646a160f79c1fdf6358d271b70a` and in its parent. The fix is bound to the verified source contract and does not depend on an inaccurate single-commit attribution.

## Safety Boundaries

- The new matcher accepts either no keyword or exactly `session_key=session_key`. Extra keywords, wrong names or values, `**kwargs`, and missing or extra positional arguments still fail closed.
- The media and local filters must independently satisfy their exact assignment contracts. Patch markers, manifests, backups, restore, and corrupt-marker protections are unchanged.
- This release does not change Feishu API payloads, card ownership, Gateway runtime events, callback authentication, delivery UUIDs, or the archived `legacy/` runtime.

## Verification

- Exact PR #241 head `5e75650b0f147a24e65d5f0e499fe8b5a3f8f22f`: focused patcher/detection/CLI-install regression **`460 passed, 1 skipped`**; all six adversarial call shapes were rejected.
- Real upstream `gateway/platforms/base.py`: apply succeeded, a second apply was idempotent, and strict remove restored the original bytes.
- Full pytest in a fresh Python 3.12 regular-wheel environment: **`3330 passed, 5 skipped in 569.93s`**; `git diff --check`: **passed**.
- All 12 GitHub checks on PR #241 passed; exact merge: `7fcf3cbd67d3a5100739e9e3d3d7cdcce080cb62`. Release-candidate CI, exact release merge, annotated tag, public tagged install, and Release assets/checksums: **pending the final gates**.
- Real Feishu client smoke: **not run**. This fix only changes installer AST-contract recognition; automation is not represented as platform acceptance.

## Credits

Thanks to @lanx214 for reporting the newer-Hermes installer incompatibility and providing a Linux reproduction.

Thanks to @PureWhiteWu for PR #241's strict matcher, installer/detection regressions, and byte-exact restore verification.
