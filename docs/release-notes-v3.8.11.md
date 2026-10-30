# V3.8.11 Release Notes

V3.8.11 is a focused hotfix for `/hfc` diagnostic commands in real Feishu/Lark chats.

## What Changed

- **No duplicate native unknown-command reply**: accepted `/hfc` commands now stay owned by the plugin. `/hfc status` can render the Hermes Agent card without also triggering Feishu's gray native `Unknown command /hfc` message.
- **Fast command ACK**: the sidecar `/commands` endpoint returns `handled: true` as soon as it accepts an `/hfc` request, then sends the Feishu card in the background. Slow Feishu delivery no longer makes the Gateway hook assume the command was unhandled.
- **Earlier Gateway interception**: the installer patch intercepts `/hfc` before Hermes' native slash-command fallback path while keeping unknown or unsupported commands fail-open.
- **Real event text fallback**: hook runtime command parsing now reads `event.text` and `event.content` when Gateway event helpers do not expose the slash-command text.

## Upgrade

```bash
export HFC_VERSION=v3.8.11
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.11
bash install-docker.sh
```

After upgrading, rerun `setup` or `install` so the Hermes Gateway patch and runtime package are refreshed, then send `/hfc status` in Feishu/Lark. The expected result is one Hermes Agent card and no gray native `Unknown command /hfc` reply.

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.11-macos.tar.gz`
- `hermes-feishu-card-v3.8.11-linux.tar.gz`
- `hermes-feishu-card-v3.8.11-windows.zip`
- `hermes-feishu-card-v3.8.11-checksums.txt`

## Verification

- Integration coverage proves `/commands` returns before a blocked Feishu command-card send completes.
- Hook runtime coverage verifies `/hfc` command text extraction from Gateway event text/content.
- Patcher coverage verifies the early `/hfc` interception block is installed before Hermes' native unknown slash-command response.
- Real Feishu/Lark smoke confirmed `/hfc status` returns the card without the duplicate gray unknown-command message.
