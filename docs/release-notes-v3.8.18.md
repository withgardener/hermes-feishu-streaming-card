# V3.8.18 Release Notes

V3.8.18 fixes cron delivery into Feishu/Lark topic-group threads. The change was contributed by @colinaaa in [PR #91](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/91) and closes [issue #90](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/90).

## Fixed

- Cron jobs created from a Feishu topic-group thread now preserve `thread_id` and send the streaming card back into that thread instead of creating a new topic.
- Scheduler-resolved Feishu targets take priority over the job origin, with an explicit environment fallback retained for compatible deployments.
- Thread ids from non-Feishu origins are ignored, preventing cross-platform routing data from leaking into Feishu delivery.

## Contribution

- Thank you to @colinaaa for the original implementation and regression coverage in PR #91. The merge preserved the contributor's original commit and added maintainer hardening for mixed-platform cron routing.

## Upgrade

Existing configurations remain compatible. For a pinned Docker/container install:

```bash
export HFC_VERSION=v3.8.18
bash install-docker.sh
```

After upgrading, restart Hermes Gateway and run `doctor --explain` if cron cards or topic routing need verification.

## Validation

- Full test suite: `765 passed`
- GitHub Actions main CI: pytest 3.9, pytest 3.12, and PowerShell installer all passed.

## Release Assets

- `hermes-feishu-card-v3.8.18-macos.tar.gz`
- `hermes-feishu-card-v3.8.18-linux.tar.gz`
- `hermes-feishu-card-v3.8.18-windows.zip`
- `hermes-feishu-card-v3.8.18-checksums.txt`
