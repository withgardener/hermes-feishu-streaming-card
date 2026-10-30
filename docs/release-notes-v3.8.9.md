# V3.8.9 Release Notes

V3.8.9 fixes Feishu/Lark topic reply card continuity.

## What Changed

- Topic replies now keep streaming updates on the original card even when Hermes uses a different internal streaming `message_id` after the first card is created.
- The sidecar resolves active topic sessions by `reply_to_message_id` before creating a new session, so `tool.updated`, `answer.delta`, `thinking.delta`, `message.completed`, and `system.notice` events keep PATCHing the same Feishu/Lark card.
- Session-scoped native Hermes notices inside topics now return `applied: true` when they are folded into the active card timeline. This prevents the adapter wrapper from also sending the same notice as a gray native Feishu/Lark text message.
- Recognized Hermes system notices are now suppressed even if the card delivery attempt times out, preventing the observed "card plus external gray notice" duplicate in Feishu/Lark topic panes.
- Hook runtime stream events preserve the Feishu reply anchor from Relay `source.message_id`, covering Hermes v0.18.x WebSocket long-connection topic flows.

## Upgrade Notes

No configuration change is required for single-profile deployments.

After upgrading, rerun install/setup so the Hermes Gateway runtime imports the refreshed hook runtime:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli doctor --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
```

For Docker installs, set:

```bash
export HFC_VERSION=v3.8.9
bash install-docker.sh
```

## Verification

- `uv run --extra test pytest tests/unit/test_hook_runtime.py -q -k "stream_event_carries_topic_reply_anchor"`
- `uv run --extra test pytest tests/integration/test_server.py -q -k "topic_stream_event_with_reply_anchor_updates_existing_card or topic_system_notice_with_reply_anchor_updates_existing_card"`
- `uv run --extra test pytest tests/unit/test_hook_runtime.py -q -k "native_feishu_system_notice_send_suppresses_text_when_card_times_out"`
- `uv run --extra test pytest tests/unit/test_hook_runtime.py tests/integration/test_server.py tests/integration/test_feishu_client_http.py tests/unit/test_feishu_client.py -q`
- Local Hermes + Lark topic smoke: create or open a topic, send a normal agent prompt, verify the card appears inside the topic, tool/timeline events update the same card, and runtime notices do not duplicate as gray native text outside the card.

## Release Assets

GitHub Releases include:

- `hermes-feishu-card-v3.8.9-macos.tar.gz`
- `hermes-feishu-card-v3.8.9-linux.tar.gz`
- `hermes-feishu-card-v3.8.9-windows.zip`
- `hermes-feishu-card-v3.8.9-checksums.txt`
