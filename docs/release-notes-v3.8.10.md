# V3.8.10 Release Notes

V3.8.10 improves group-chat diagnostics and makes tool details more useful inside the Feishu/Lark card timeline.

## What Changed

- **Group status is explicit**: `/hfc status` now detects group/topic/channel contexts and explains whether the chat is bound to a bot, whether fallback/default routing is being used, and which `bots bind-chat ...` command to run next.
- **Clear boundary for @bot and allowlists**: Hermes Gateway remains the source of truth for @robot triggering and group allowlist admission. The sidecar reads `bindings.group_rules` only for safe diagnostics and does not expose raw chat/user ids.
- **Slash command guidance in groups**: group `/hfc status` now documents that `/new`, `/model`, `/reset`, and similar commands first pass Hermes group admission before using standalone command cards. `/update` continues to use Hermes' background upgrade behavior.
- **Richer tool timeline**: `tool.updated` cards can display argument summaries, duration, and failure reason when those values are available from Hermes runtime locals.
- **Installer warning cleanup**: issue #79 is included in this release. `install.sh` and `install-docker.sh` suppress pip's root-user warning by default and retry recoverable PEP 668 externally managed environments with a concise explanation.

## Upgrade

```bash
export HFC_VERSION=v3.8.10
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.10
bash install-docker.sh
```

After upgrading, run:

```bash
python3 -m hermes_feishu_card.cli doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
```

For a group chat, send `/hfc status` in the target group. If the group is not bound, the card will show the suggested `bots bind-chat` command. Real @robot triggering and user allowlist behavior should still be configured and verified in Hermes.

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.10-macos.tar.gz`
- `hermes-feishu-card-v3.8.10-linux.tar.gz`
- `hermes-feishu-card-v3.8.10-windows.zip`
- `hermes-feishu-card-v3.8.10-checksums.txt`

## Verification

- Tool detail extraction and rendering tests cover arguments, duration, and failure reason.
- Hook-runtime tests cover `tool.updated` metadata extraction from Hermes locals.
- Bot routing tests cover safe group-rule diagnostics without leaking raw ids.
- Integration tests cover group `/hfc status` binding hints and slash-command guidance.
