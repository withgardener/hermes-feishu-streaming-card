# Hermes Feishu Streaming Card V4.3.1

[中文](release-notes-v4.3.1.md) | [English](release-notes-v4.3.1.en.md)

V4.3.1 是 Hermes 0.20 Hybrid 交互与 v4.3.0 persistent service 的可靠性热修。它修复的不是“飞书完全没有事件”这一单一假设，而是 Issue #216 后续真实复测暴露的两段本地链路问题：按钮点击已经让 Hermes 继续，但卡片没有继续显示流式正文/思考；显式 text fallback 的第一条回复也没有唤醒等待中的交互。

## Issue #216：点击后继续流式更新

- pending clarify/approval 改用飞书 WebSocket card-action 通道可回调的 interactive-card payload；按钮 `value` 携带受约束的 interaction id、choice、callback token 与 exact profile identity。
- Hermes hook 把 profile identity 同时带入 action/context，再转发到 sidecar `/card/actions`。sidecar 因此能命中原 profile/session，而不是在严格 profile 校验处返回 404。
- sidecar 仍通过签名的 loopback runtime listener 直接唤醒原 Hermes pending handle/future；点击成功后，同一 turn 的 answer/thinking delta 继续进入最新卡片，不需要再发一句话推动终态刷新。
- 显式 `card.interaction_mode: text` 在任何 session/interaction mutation 前拒绝 runtime callback ownership，让 Hermes 原生编号/文本 interceptor 接收第一条回复；不会同时保留卡片 waiter 与文本 waiter。
- `/health` 新增脱敏的 runtime callback attempts/successes/failures 与最后结果分类，便于区分按钮没到 sidecar、listener 拒绝、超时、过期和成功；不记录 choice、callback token、chat/user/profile id 或回答正文。

## PR #226：persistent service enable

- runtime identity 统一使用生产代码实际产生的 `python-sha256:<64 hex>`，不再因错误期待 `sha256:` 而让 `enable` 永久拒绝。
- systemd `WorkingDirectory` 使用路径值语义，不再套用 `ExecStart` 参数 quoting；同时拒绝 relative/control-character 输入，并转义 `%` 与反斜杠，避免 specifier 展开或行续接。
- tokenless sidecar 的 `/health` 明确返回空 `process_token_hash`；有 token 时只返回 SHA-256，不回显 token。persistent service health 对账因此不会把 `None` 与空字符串误判为漂移。

## 真实环境证据

- 固定 Hermes `v2026.8.3` / `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`，安装候选 wheel 后通过本机 Hermes Gateway 与飞书 WebSocket 长连接完成真实按钮点击。
- 两次真实点击均到达 sidecar runtime listener 并返回 resolved；交互后卡片继续显示新一轮流式结果，未再要求额外发送一句话。
- 真实标识符、callback token、凭据、回答正文与截图不进入仓库或发布说明。

## 兼容与安全边界

- fixed-tag capability proof、17 个 Hybrid patch group、7 个 target、V3 installer ownership 与 byte-for-byte restore 不放宽。
- callback 仍绑定 exact session/profile/interaction/operator/chat/expiry；重复、冲突、过期、错误 profile 和未知 descriptor fail-closed。
- `legacy/` 继续只读归档，PR #203 不进入 active runtime。

## 贡献者

- 感谢 [saulgoodmanngabriel](https://github.com/saulgoodmanngabriel) 提交 [Issue #216](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/216)，并感谢 [zhangzq](https://github.com/zhangzq) 在 Hermes 0.20 上复测，帮助把“点击无效”进一步拆解为“runtime 已继续、但流式/思考更新丢失”和 text fallback 首次回复未唤醒。
- 感谢 [RanHuang](https://github.com/RanHuang) 提交 [PR #226](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/226)，定位 runtime identity、systemd `WorkingDirectory` 与 tokenless health 对账的三个根因；最终实现保留这些发现，并补充更严格的路径转义和攻击性回归。
- 本轮同时把中英文 README 与历史 release/PR/issue/commit/co-author 记录重新对账，补回此前版本中遗漏的代码作者、PR 方案作者、Issue 报告者和真实复测者。GitHub Contributors 图只统计进入 Git 历史的 commit；纯 Issue/评论贡献仍在 README 与 release notes 中署名。

## 验证

- 完整 pytest：`3245 passed, 6 skipped in 425.58s`。
- `python -m build --no-isolation` 成功生成 `hermes_feishu_streaming_card-4.3.1.tar.gz` 与 `hermes_feishu_streaming_card-4.3.1-py3-none-any.whl`。
- 全新 Python 3.12 venv 只安装候选 wheel 与公开依赖后，package/distribution version 均为 `4.3.1`，import origin 位于该 venv 的 `site-packages`，Hermes plugin entrypoint 精确为 1，24 个 provenance slices 齐全，主 CLI 与 `enable/disable --help` 均 exit 0。
- `git diff --check`、exact merge SHA、远端 CI、annotated tag、public tag/install 与 Release assets 在发布流程中逐项记录，未完成前不写成通过。
