# V4.0.14

V4.0.14 修复 Issue #142：当长任务主卡已经不在 sidecar 内存中时，Hermes 的连续 `Working` heartbeat 不再创建多张互相矛盾的独立卡片。

## 长任务 heartbeat 生命周期

- heartbeat 明确标记为非终态（`non-terminal`）；独立卡保持“运行中”，不会再出现 Header 为“运行中”、副标题却是“已完成”的状态冲突。
- 同一用户消息锚点下的 6 分钟、9 分钟等连续 heartbeat 使用稳定的 independent message id，后续通知 PATCH 同一张卡。
- 稳定身份包含 chat 与原始用户消息锚点；同一群聊中的并发长任务不会互相覆盖。
- 最终 `message.completed` 仍通过 reply-anchor alias 找到并完成这张卡，不会留下永久运行卡。

## 可靠投递边界

- `unknown` delivery 仍只回退固定的通用提示，不重复原始运行通知文本。
- 如果某次结果无法确认，后续 heartbeat 会使用相同独立身份回到原生命周期，避免再次创建新卡。
- `not_sent`、未知通知文本、非 Feishu 平台和其他既有 fail-open 行为保持不变。

## 验证

- 覆盖 heartbeat 非终态分类、同锚点复用、不同锚点隔离、orphan 6/9 分钟更新、最终完成和 unknown delivery 后恢复。
- 完整自动化通过：`1488 passed, 3 skipped`；sdist/wheel 构建、隔离 Python 3.12 `site-packages` 导入 `4.0.14` 和 CLI smoke 均通过。
- 感谢 @ati121 在 Issue #142 中报告长任务重复卡片和矛盾状态。

## Release assets

- `hermes-feishu-card-v4.0.14-macos.tar.gz`
- `hermes-feishu-card-v4.0.14-linux.tar.gz`
- `hermes-feishu-card-v4.0.14-windows.zip`
- `hermes-feishu-card-v4.0.14-checksums.txt`
