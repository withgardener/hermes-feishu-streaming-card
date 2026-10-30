# V3.8.7 Release Notes

V3.8.7 is a compatibility hotfix for issue #75.

## What Changed

- Newer Hermes streams may begin with `answer.delta`, `thinking.delta`, `tool.updated`, or `message.completed` without first sending `message.started`.
- The sidecar now treats those first message events as session-creating events, sends the initial Feishu/Lark card, and then applies the event normally.
- Existing `message.started`, interaction card, and cron completion paths remain compatible.
- V3.8.6's Docker/source-stripped Hermes version fallback remains unchanged.

## Verification

- `python -m pytest tests/integration/test_server.py::test_message_event_without_started_creates_initial_card -q`
- `python -m pytest tests/integration/test_server.py -q`
- `python -m pytest -q`

## Release Assets

GitHub Releases include:

- `hermes-feishu-card-v3.8.7-macos.tar.gz`
- `hermes-feishu-card-v3.8.7-linux.tar.gz`
- `hermes-feishu-card-v3.8.7-windows.zip`
- `hermes-feishu-card-v3.8.7-checksums.txt`
