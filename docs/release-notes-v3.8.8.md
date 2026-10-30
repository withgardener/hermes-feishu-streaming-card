# V3.8.8 Release Notes

V3.8.8 folds native Hermes runtime/status notices into the Feishu/Lark card experience.

## What Changed

- Added `system.notice` events for Hermes notices that previously appeared as separate gray native messages.
- Covered common runtime notices: `Working` long-running heartbeats, Codex context-window/auto-compaction notices, automatic session reset notices, skill-loading notices, self-improvement review notices, and context-compression notices.
- Session-scoped notices enter the active card's auxiliary timeline when the card is still updateable.
- Task-external notices or notices for already-completed sessions become compact standalone notice cards.
- Heartbeat-style notices reuse the same `notice_id`, so repeated `Working — iteration ...` updates refresh one timeline entry instead of adding many entries.
- If the sidecar is unavailable, a notice is unknown, or card delivery fails, Hermes native text fallback remains available.

## Upgrade Notes

No configuration change is required for single-profile deployments.

After upgrading, rerun install/setup so the Hermes Gateway runtime imports the refreshed hook runtime:

```bash
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli doctor --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
```

For Docker installs, set:

```bash
export HFC_VERSION=v3.8.8
bash install-docker.sh
```

## Verification

- `python -m pytest tests/unit/test_events.py::test_parses_system_notice_event tests/unit/test_session.py::test_system_notice_records_and_updates_timeline_entry tests/unit/test_session.py::test_independent_system_notice_becomes_completed_notice_card tests/unit/test_render.py::test_render_timeline_styles_system_notices_as_compact_status_lines tests/unit/test_render.py::test_render_independent_notice_card_uses_notice_title_and_status tests/integration/test_server.py::test_independent_system_notice_without_started_sends_notice_card tests/unit/test_hook_runtime.py::test_native_feishu_system_notice_send_posts_sidecar_and_suppresses_text tests/unit/test_hook_runtime.py::test_native_feishu_system_notice_retries_as_independent_card_when_current_session_done tests/unit/test_hook_runtime.py::test_native_feishu_system_notice_edit_updates_same_card -q`
- `python -m pytest tests/unit/test_events.py tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_hook_runtime.py tests/integration/test_server.py -q`
- `python -m pytest -q`
- Local Hermes runtime install and Lark smoke with an independent notice card plus a session-scoped notice timeline update.

## Release Assets

GitHub Releases include:

- `hermes-feishu-card-v3.8.8-macos.tar.gz`
- `hermes-feishu-card-v3.8.8-linux.tar.gz`
- `hermes-feishu-card-v3.8.8-windows.zip`
- `hermes-feishu-card-v3.8.8-checksums.txt`
