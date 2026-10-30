# V3.8.14 Release Notes

V3.8.14 adds WebSocket-native handling for Hermes agent clarify/approval card choices, closing issue #86.

This release includes PR #87 from @colinaaa, with a maintainer regression test added before merge.

## What Changed

- **Clarify/approval buttons work over Feishu/Lark WebSocket**: `interaction.select` card-action clicks are now handled by the Hermes adapter hook and forwarded to the sidecar `/card/actions` endpoint.
- **No public callback URL required**: local/private sidecar deployments can keep agent clarify/approval choices as card buttons instead of falling back to numbered text.
- **Sidecar validation remains the security boundary**: `/card/actions` still validates `interaction_id` plus the per-interaction callback token, and also checks `open_chat_id` when the callback payload includes it.
- **Rejected or expired interactions fail safely**: if the sidecar rejects the click or returns no updated card, the hook returns an empty Feishu callback response instead of crashing or falling through to the original adapter handler.

## Upgrade

```bash
export HFC_VERSION=v3.8.14
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.14
bash install-docker.sh
```

After upgrading, reinstall the Hermes hook so the WebSocket card-action handler in `gateway/run.py` points at this package version:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
hermes gateway restart
```

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.14-macos.tar.gz`
- `hermes-feishu-card-v3.8.14-linux.tar.gz`
- `hermes-feishu-card-v3.8.14-windows.zip`
- `hermes-feishu-card-v3.8.14-checksums.txt`

## Verification

- Full pytest suite: `739 passed`.
- `git diff --check`.
- PR #87 focused hook-runtime suite after the rejection-path test: `154 passed`.
