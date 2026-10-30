# V4.0.21 发布说明

发布日期：2026-07-28

V4.0.21 是针对 Issue #155 的内容完整性热修，并为 Issue #147 固化图片与 `system.notice` 的组合回归。它不改变卡片 UI 或配置。

## Issue #155：显式 answer/tool 归档边界

- 只有明确的 `answer -> tool` 边界，才允许把该答案片段归入“思考与工具”时间线。
- 对 `tool -> answer -> completed`，较早的工具不能成为归档依据；完成态保留整个用户可见答案，不能仅因本轮曾出现工具就剥离流式前缀。
- 对多个 `answer -> tool` 片段，仍按各自的显式后续工具边界依次归档，终态答案保持可见。

## Issue #147：图片与 notice 组合回归

- 自动化回归覆盖已接管的完成事件：卡片正文只保留一次，匹配的原生媒体文本只抑制一次，native image 仍由 Hermes 原生媒体发送器投递。
- 同一轮中，已 accepted 的排队 `system.notice` 不产生 uncertain-delivery warning；无关的后续原生文本不应被抑制。
- 既有 `MEDIA:` 清理、附件摘要和 `native_delivery=required` 语义保持不变。

## 验证边界

- Task 1 的答案顺序聚焦回归为 `74 passed`；Task 2 的图片/notice 组合回归为 `277 passed`，且未发现需要运行时代码改动的新根因。
- 2026-07-28 真实飞书验收：图片回合观测到 1 条带标记、非“生成中”的 interactive completion card 与 1 条 native image，且没有 uncertain-delivery warning。正常工具回合的两段答案保留在同一张卡，bot 原生标记重复为 0。
- sidecar 最终 metrics 为 `events_received/events_applied=23/23`、1 次发送成功、16 次更新成功；event rejected、auth rejection、send/update failures、notice uncertain warnings 与 notice update failures 均为 0。Gateway 日志确认 Feishu WebSocket 已连接。
- Hermes venv site-packages 中的候选 runtime 为 4.0.21。本验收不宣称截图或桌面/移动端视觉 QA，也不扩大为真实故障注入结论。
- 最终本地发布门禁：完整 pytest 为 `1526 passed, 4 skipped in 53.56s`。`uv build` 成功生成 `hermes_feishu_streaming_card-4.0.21.tar.gz` 与 `hermes_feishu_streaming_card-4.0.21-py3-none-any.whl`。
- 干净 Python 3.12 venv 从 wheel 安装后，import 位于 `site-packages`；package version 与 distribution version 均为 `4.0.21`，存在 `hermes-feishu-card = hermes_feishu_card.cli:main`，CLI --help exit 0。
- 公开 tagged installer 与 Release assets 仍待 post-tag 验证。
- 本说明不包含真实 chat/message/user 标识符、凭据、token 或本机路径。

## 升级

```bash
export HFC_VERSION=v4.0.21
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```
