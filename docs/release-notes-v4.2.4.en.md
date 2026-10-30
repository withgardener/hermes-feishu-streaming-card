# Hermes Feishu Streaming Card V4.2.4

Release date: 2026-08-01

V4.2.4 fixes Issue #175: consecutive Feishu/Lark topic replies quoting the same message no longer reuse and overwrite the first reply card. Every new user message creates an independent card, preserving the previous turn's content and reasoning/tool timeline.

## Fix

- The Gateway hook now gives `message.started` the real incoming `message_id`, falling back to the reply anchor only when that ID is unavailable.
- For `message.started`, the sidecar creates a direct new session instead of routing through an active `reply_to_message_id` alias to an older card.
- In-turn `thinking.delta`, `answer.delta`, and tool events keep reply alias correlation, so streaming content continues to update the new card in place.
- A real HTTP `/events` integration regression proves that two replies quoting the same message send two cards and that the second turn's delta updates only the second card.

## Compatibility and boundaries

- The fix covers the reported Hermes v0.19.1 environment while preserving existing Hermes compatibility branches and fail-open behavior.
- Native duplicate suppression, card lifecycle, `/update` safety boundaries, and installer patch ownership are unchanged.
- Thanks to [Cassius0924](https://github.com/Cassius0924) for PR #177 and the report that the real Feishu topic scenario passes. The maintainer release gate covers patcher unit tests, sidecar HTTP integration, full pytest, package builds, CI, and the exact merge SHA.

## Verification

- The exact PR #177 head passed every GitHub Actions job.
- Full pytest: `2311 passed, 5 skipped`; `git diff --check`, sdist/wheel, and clean isolated Python `site-packages` package/distribution/CLI provenance are included in the release gate.
- After installing the public tag, reply twice to the same message in a real Feishu topic: two independent cards should appear, the second should stream in place, and the first should remain unchanged.

## Install

```bash
export HFC_VERSION=v4.2.4
bash install.sh
```

After upgrading an existing installation, rerun the official `setup` / `install` flow so the Hermes runtime venv, managed hook, and sidecar all use V4.2.4. Do not edit `gateway/run.py` by hand.

## Release assets

- `hermes-feishu-card-v4.2.4-macos.tar.gz`
- `hermes-feishu-card-v4.2.4-linux.tar.gz`
- `hermes-feishu-card-v4.2.4-windows.zip`
- `hermes-feishu-card-v4.2.4-checksums.txt`

Verify downloaded files against `hermes-feishu-card-v4.2.4-checksums.txt`.
