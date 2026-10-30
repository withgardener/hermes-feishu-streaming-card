# V3.8.17 Release Notes

V3.8.17 fixes cron Feishu/Lark card delivery when Hermes cron jobs use routing-intent `deliver` values such as `origin`, `all`, or `origin,all`. The core fix was contributed by @zayn-0101 in PR #77, with maintainer hardening before release.

## What Changed

- **Cron `deliver=origin/all` sends cards again**: cron completions now resolve routing-intent tokens through the scheduled job origin or pre-resolved delivery targets instead of treating `origin` / `all` as real platforms and falling back to plain text.
- **`deliver=local` remains no delivery**: the fix intentionally keeps `local` out of the routing-intent set, so local-only cron jobs do not unexpectedly send Feishu cards.
- **Compatibility hardening**: dict-shaped `deliver` values such as `{"platform": "feishu", "chat_id": "oc_xxx"}` remain supported, non-Feishu origin chat ids are not reused for Feishu delivery, and the installed cron hook only pre-resolves targets when Hermes exposes the helper.

## Upgrade

```bash
export HFC_VERSION=v3.8.17
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.17
bash install-docker.sh
```

After upgrading, reinstall the Hermes hook so `gateway/run.py` uses this package version:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
hermes gateway restart
```

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.17-macos.tar.gz`
- `hermes-feishu-card-v3.8.17-linux.tar.gz`
- `hermes-feishu-card-v3.8.17-windows.zip`
- `hermes-feishu-card-v3.8.17-checksums.txt`

## Verification

- Cron/hook/installer focused suite: `281 passed`.
- Package/docs focused suite: `37 passed`.
- Full pytest suite: `752 passed`.
- `git diff --check`.
