# Hermes Feishu Streaming Card V4.2.4

发布日期：2026-08-01

V4.2.4 修复 Issue #175：在飞书/Lark 话题中连续引用同一条消息时，第二条及后续回复不再复用并覆盖第一张回复卡。每条新的用户消息都会创建独立卡片，前一轮内容与思考/工具时间线保持不变。

## 修复内容

- Gateway hook 的 `message.started` 现在优先使用真实入站 `message_id`；只有该 ID 缺失时才回退到 reply anchor。
- sidecar 收到 `message.started` 时直接建立新 session，不再通过活动中的 `reply_to_message_id` alias 路由到旧卡片。
- 同一轮的 `thinking.delta`、`answer.delta` 与 tool 事件仍保留 reply alias 关联，因此流式内容继续原位更新本轮新卡。
- 新增真实 HTTP `/events` 集成回归：两次引用同一消息会发送两张卡，第二轮 delta 只更新第二张卡。

## 兼容性与边界

- 修复适用于报告环境 Hermes v0.19.1，也保留既有 Hermes 兼容分支与 fail-open 行为。
- 未改动原生重复抑制、卡片生命周期、`/update` 安全边界或 installer 的 patch 所有权。
- 感谢 [Cassius0924](https://github.com/Cassius0924) 提交 PR #177，并报告真实飞书话题场景已通过；维护者发布门禁覆盖 patcher 单元测试、sidecar HTTP 集成测试、完整 pytest、构建、CI 与精确 merge SHA。

## 验证

- PR #177 的精确 head 已通过全部 GitHub Actions jobs。
- 完整 pytest：`2311 passed, 5 skipped`；`git diff --check`、sdist/wheel 与干净隔离 Python `site-packages` 包/distribution/CLI provenance 均纳入发布门禁。
- 正式 tag 发布后，建议在真实飞书话题中连续两次引用同一消息：应出现两张独立卡片，第二张流式更新且第一张不变。

## 安装

```bash
export HFC_VERSION=v4.2.4
bash install.sh
```

升级现有安装后请重新运行官方 `setup` / `install`，让 Hermes runtime venv、managed hook 与 sidecar 使用同一个 V4.2.4 包；不要手工修改 `gateway/run.py`。

## Release assets

- `hermes-feishu-card-v4.2.4-macos.tar.gz`
- `hermes-feishu-card-v4.2.4-linux.tar.gz`
- `hermes-feishu-card-v4.2.4-windows.zip`
- `hermes-feishu-card-v4.2.4-checksums.txt`

下载后请按 `hermes-feishu-card-v4.2.4-checksums.txt` 核对 SHA-256。
