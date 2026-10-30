# Hermes Feishu Streaming Card V4.3.3

[中文](release-notes-v4.3.3.md) | [English](release-notes-v4.3.3.en.md)

V4.3.3 修复首回复需要从当前飞书消息创建 thread、但 Hermes 尚未提供具体 `thread_id` 时的投递连续性。该 placement 现在绑定到当前 `CardSession`，而非从后续 event identity 重新推断。

## 修复内容

- 当 Hermes 显式发送 `reply_in_thread=true` 和真实 `reply_to_message_id` 时，首张 schema 2.0 流式卡使用飞书 reply API 创建 thread；普通、重复与 runtime-admission clarify/approval 卡都继续使用同一锚点和 placement。
- opt-in completion notification 复用 session 的 `reply_in_thread` 意图。没有 concrete `thread_id` 时，它仍作为该锚点的 thread reply 发送，不会落到主群。
- `FeishuClient.send_text_message()` 现在与 card-send 路径一致：`reply_in_thread=true` 或非空 `thread_id` 表示 thread placement；任一路径缺少 `reply_to_message_id` 都会 fail-closed，拒绝请求而不是发送顶层文本。没有 thread placement intent 的默认路径保持现有兼容行为。

## 安全边界

- 只有明确的 thread intent 和非空 reply anchor 才会触发 client reply 路径；缺 anchor 是拒绝，不是 best-effort top-level fallback。server 侧的 Hermes event 路径继续只接受 `om_` anchor。
- 原 schema 2.0 streaming message 仍是唯一 PATCH owner；legacy interaction card、callback token、chat/operator/profile binding、过期、幂等、Hermes patch ownership 与归档 `legacy/` runtime 均未改变。
- 本版本不包含 PR #229 的 daemon listener 修改；`pytest-macos` required check 已在两个连续 head 上对同一 subprocess test 超时失败，仍等待作者修复。

## 验证状态

- 本地回归覆盖首回复没有 concrete `thread_id` 时的 card/interaction/completion placement，以及 text-send 缺 anchor 时不获取 token、不调用 Feishu API。
- 本地完整 pytest **`3267 passed, 6 skipped`**，`git diff --check`、sdist/wheel 构建与全新 Python 3.12 venv 的 wheel-only provenance、唯一 Hermes plugin entrypoint、24 个 provenance slices 和 CLI help smoke 均已通过。
- PR #232 candidate HEAD `f7de533d67f9e50afcd2c4d80fad89b572054605` 的远端 Tests run `32657674121`（10 个 job）与 CodeQL run `32657674120` 均已通过。
- exact merge SHA、公开 tag/install、Release assets/checksums 与真实 Feishu/Lark 客户端验收尚未在本 release candidate 中完成；自动化不替代真实客户端证据。

## 真实飞书待验收

- 在测试群顶层消息触发首回复建 thread，确认首卡、普通与 runtime-admission interaction、completion notification 均留在同一 thread，主群没有 top-level fallback。
- 显式 thread intent 缺 anchor 时，确认 completion notification 不发送顶层文本，并只记录脱敏拒绝分类。
