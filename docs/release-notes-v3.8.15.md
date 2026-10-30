# V3.8.15 Release Notes

V3.8.15 fixes a follow-up issue #82 recurrence where completed cards could still be followed by a duplicate native Feishu/Lark reply when the ongoing Hermes session included an input file such as a `.docx` resume.

## What Changed

- **Input file context stays card-only**: structured `files` / `file` locals are still shown as card attachment summaries, but no longer make the completion hook keep Hermes' native final text reply.
- **Real output media/file paths remain fail-open**: if the final answer explicitly contains `MEDIA:/tmp/...` or a local file path, native delivery is still preserved so Hermes can send the actual file/media object.
- **Structured output media remains protected**: `media_files`, `media`, `image_files`, `audio_files`, and `video_files` still mark native delivery as required.

## Upgrade

```bash
export HFC_VERSION=v3.8.15
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.15
bash install-docker.sh
```

After upgrading, reinstall the Hermes hook so `gateway/run.py` uses this package version:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
hermes gateway restart
```

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.15-macos.tar.gz`
- `hermes-feishu-card-v3.8.15-linux.tar.gz`
- `hermes-feishu-card-v3.8.15-windows.zip`
- `hermes-feishu-card-v3.8.15-checksums.txt`

## Verification

- Focused runtime/server tests: `222 passed`.
- Full pytest suite: `740 passed`.
- `git diff --check`.
