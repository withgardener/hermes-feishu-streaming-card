# Hermes Feishu Streaming Card V4.3.8

[中文](release-notes-v4.3.8.md) | [English](release-notes-v4.3.8.en.md)

V4.3.8 fixes three runtime-reliability gaps: reboot persistence after guided setup, the consecutive batch-clarify race, and Feishu/Lark HTTP proxy support. Sequence, service-ownership, and local-network isolation boundaries remain intact.

## Fixes

- Issue #244: guided `setup` now enables the HFC-owned persistent service by default when the Linux systemd user manager works and linger is already enabled. When the capability is unavailable, setup explicitly warns that the sidecar will not survive a host reboot, starts the existing transient path, and prints the exact `enable` command; `setup --transient` explicitly opts out.
- Issue #245: an authenticated card action's internal `interaction.completed` no longer advances the Hermes `/events` transport `last_sequence`. The next `interaction.requested` in a batch clarify is accepted even when it uses the same next sequence immediately after the first click, and the first callback card is snapshotted under the session lock so it cannot include the second prompt.
- PR #242: remote Feishu/Lark HTTP requests now honor standard proxy environment variables. Loopback, private, link-local, and unspecified destinations still bypass environment proxies so local sidecars, mocks, and acceptance traffic are not exported accidentally.
- CLI `status` integration tests now use an isolated config and state directory instead of reading a maintainer's live local sidecar state.

## Safety Boundaries

- `setup` never runs `loginctl enable-linger`, invokes sudo, enters the system manager, or writes `/etc`. It uses the existing transient fallback when the complete persistent capability is unavailable.
- Transport events retain strict monotonic sequence validation. Only an out-of-band card callback that already passed the existing authentication and interaction-identity checks avoids advancing the transport watermark.
- Persistent unit/manifest ownership, SHA-256 reconciliation, safe stop, drift refusal, and `disable` cleanup contracts are unchanged.
- Proxy support does not change Feishu API payloads, callback authentication, card ownership, delivery UUIDs, or the archived `legacy/` runtime.

## Verification

- Proxy client unit tests and a real local HTTP proxy integration: **passed (`81 passed`)**.
- Session/hook/server batch-clarify and sequence regression suite: **passed (`937 passed`)**; the new deterministic race test overlaps the first callback with the second `/events` request.
- Persistent/process/install focused matrix: **passed (`649 passed, 5 skipped`)**; fresh normal-wheel process lifecycle suite: **`8 passed`**.
- Full pytest in a fresh Python 3.12 normal-wheel environment: **`3343 passed, 6 skipped in 690.84s`**; `git diff --check`: **passed**. Release-PR CI, exact merge SHA, annotated tag, public tagged install, and Release assets/checksums remain final publication gates.
- Real Feishu/Lark client smoke: **not run**. Real Linux systemd-user + linger host smoke: **not run**; automation, mocks, and CI are not represented as real-platform acceptance.

## Credits

Thanks to [nasvip](https://github.com/nasvip) for Issue #244's production report of a sidecar silently remaining offline after a host reboot and for the installer-experience suggestions.

Thanks to [Timeral](https://github.com/Timeral) for Issue #245's reproducible timing window for consecutive batch-clarify prompts.

Thanks to [PureWhiteWu](https://github.com/PureWhiteWu) for implementing PR #242's proxy-environment support and regression coverage; the original code authorship is preserved in Git history.
