# V3.8.12 Release Notes

V3.8.12 is a focused hotfix for issue #82: duplicate native Feishu/Lark replies could still appear after a completed streaming card when the answer carried attachment summaries.

## What Changed

- **Attachment summaries stay card-only**: completed cards that list generated artifacts such as `colors.csv` or `styles.csv` no longer force Hermes to send the same final answer again as a native reply.
- **Real media delivery stays protected**: `MEDIA:/tmp/...`, local file paths, `files`, `media_files`, and image/audio/video file locals still mark `native_delivery: required`, so actual native file/media delivery is not swallowed by card suppression.
- **Patcher suppression guard updated**: the Gateway completion hook now passes the preview event's `native_delivery` policy into `should_suppress_native_response(...)` instead of using a broad "any attachments means native fallback" rule.

## Upgrade

```bash
export HFC_VERSION=v3.8.12
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.12
bash install-docker.sh
```

After upgrading, rerun `setup` or `install` so the Hermes Gateway patch and runtime package are refreshed. For issue #82 specifically, retry a prompt that produces a card with attachment summaries; the expected result is one completed Hermes Agent card and no duplicate native reply containing the same final answer.

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.12-macos.tar.gz`
- `hermes-feishu-card-v3.8.12-linux.tar.gz`
- `hermes-feishu-card-v3.8.12-windows.zip`
- `hermes-feishu-card-v3.8.12-checksums.txt`

## Verification

- Full pytest suite: `728 passed`.
- `git diff --check`.
- Regression coverage for generic attachment summaries, real native media/file delivery, patcher suppression guards, and installed-hook completion event payloads.
