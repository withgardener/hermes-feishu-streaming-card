# Hermes Feishu Streaming Card V4.2.12

[中文](release-notes-v4.2.12.md) | [English](release-notes-v4.2.12.en.md)

V4.2.12 合入 @Cassius0924 的 PR #206 与 PR #205：approval 卡片现在只展示 Hermes 当前允许的授权范围，sidecar 同时拒绝未声明的输入；没有工具调用的卡片在启用 reasoning timeline 时保持稳定折叠入口，不再在运行态与终态之间切换结构。

## Approval 能力与校验

- **能力生成选项**：`smart_denied` 仅提供 once/deny；`allow_session=false` 隐藏 session/always；`allow_permanent=false` 只隐藏 always。
- **显式输入契约**：`interaction.requested.data.allow_custom_input` 贯穿 hook、event、session、renderer 与 callback。approval 默认 `false`，clarify 明确为 `true`。
- **服务端防伪**：固定选项 interaction 只接受当前卡声明的 value；伪造 button value、approval 自定义 form 与非布尔 truthy capability 均被拒绝，interaction 保持 pending。
- **Clarify 保持兼容**：单选、多选与“其他”自定义答案不变；旧事件缺少字段时仅 `kind=clarify` 兼容启用自定义输入。

## 零工具时间线

- 启用 reasoning timeline 时，零工具卡在初始加载、运行、完成与失败态始终保留“思考与工具 · 0 次工具调用”折叠入口。
- 初始加载显示“等待工具事件…”，其他空状态显示“暂无可展示的思考或工具记录。”。
- raw `thinking.delta` 继续隐藏；`show_reasoning=false` 继续使用普通 tool summary，不强制显示折叠 timeline。

## 安全与范围

- callback token、chat/operator binding、absolute expiry、interaction idempotency、topic/reply 路由和 native gray-text suppression 均未改变。
- 本版不修改归档的 `legacy/`，不手工编辑 Hermes `gateway/run.py`，也不扩大 patcher 所有权。
- 本轮不额外发送真实飞书测试消息。PR #205 的真实飞书结果属于贡献者证据；PR #206 与组合结果使用自动化、独立攻击测试和多平台 CI，不宣称维护者真实客户端复测。

## 升级

macOS / Linux：

```bash
export HFC_VERSION=v4.2.12
bash install.sh
```

Docker：

```bash
export HFC_VERSION=v4.2.12
bash install-docker.sh
```

Windows PowerShell：

```powershell
$env:HFC_VERSION = "v4.2.12"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.12/install.ps1" | iex
```

升级后运行：

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## 验证边界

- PR #206/#205 更新到同一 main 后的 GitHub 多平台 CI 全绿；合并 runtime 基线完整 pytest 为 `2481 passed, 6 skipped`。
- v4.2.12 候选 docs/package `94 passed`、聚焦矩阵 `830 passed`、完整 pytest `2481 passed, 6 skipped`；sdist/wheel、隔离 `site-packages` provenance、CLI help 与 `git diff --check` 均通过。
- 精确 merge SHA、annotated tag、Release assets、checksums 与公开 tag 安装在发布流程完成后核验。

预期 Release assets：

- `hermes-feishu-card-v4.2.12-macos.tar.gz`
- `hermes-feishu-card-v4.2.12-linux.tar.gz`
- `hermes-feishu-card-v4.2.12-windows.zip`
- `hermes-feishu-card-v4.2.12-checksums.txt`
