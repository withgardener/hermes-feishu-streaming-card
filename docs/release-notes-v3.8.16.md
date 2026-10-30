# V3.8.16 Release Notes

V3.8.16 fixes issue #89 in Feishu/Lark topic groups where the second and later messages in the same topic could show no streaming card. The fix was contributed by @colinaaa in PR #88.

## What Changed

- **Fresh cards for reused topic `message_id` values**: when a new topic turn reuses a `message_id` whose previous session is already completed or failed, the sidecar clears the stale session delivery state and sends a new card.
- **Clarify/approval turns no longer hang without a card**: second-turn `interaction.requested` flows can now render their interaction card instead of falling back to native text only.
- **Duplicate active starts stay safe**: a duplicate `message.started` while the current turn is still streaming remains ignored, so the fix does not create extra cards during normal retries.

## Upgrade

```bash
export HFC_VERSION=v3.8.16
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.16
bash install-docker.sh
```

After upgrading, reinstall the Hermes hook so `gateway/run.py` uses this package version:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
hermes gateway restart
```

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.16-macos.tar.gz`
- `hermes-feishu-card-v3.8.16-linux.tar.gz`
- `hermes-feishu-card-v3.8.16-windows.zip`
- `hermes-feishu-card-v3.8.16-checksums.txt`

## Verification

- Topic-group regression tests: `2 passed`.
- Runtime/server focused suite: `224 passed`.
- Full pytest suite: `742 passed`.
- `git diff --check`.
