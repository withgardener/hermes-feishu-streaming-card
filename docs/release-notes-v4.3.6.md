# Hermes Feishu Streaming Card V4.3.6

[中文](release-notes-v4.3.6.md) | [English](release-notes-v4.3.6.en.md)

V4.3.6 修复飞书话题场景无 reply anchor 时使用非法 `receive_id_type=thread_id` 创建消息导致的 `99992402`，并加入可配置的 approval/clarify 交互卡与 completion notification 发起人 `@` 提及。

## 修复内容

- Issue #237 / PR #238：Feishu create API 现在始终向父 `chat_id` 创建卡片，不再把 `thread_id` 作为 `receive_id_type` 或 `receive_id`。当 `reply_to_message_id` 存在时仍使用 reply API，并保留 `reply_in_thread` 语义。
- Gateway native-handoff 的真实无锚点 create 会从 adapter metadata 中移除 `thread_id`，避免 Hermes 同源 fallback 再次发出非法请求；逻辑 topic route 与稳定 UUID identity 仍保持不变。
- `completion_notify.mention: false` 不再无条件要求合法 sender `open_id`。系统/后台 turn 可以发送不带 `@` 的普通完成通知；mention 开启时仍拒绝缺失、伪造或非法身份。

## 新增能力

- PR #228：pending approval/clarify 卡片与 opt-in completion notification 可 `@` 提及任务发起人。
- `card.mentions_in_cards: false` 是总关闭开关；`card.interaction_mentions.approval`、`card.interaction_mentions.clarify` 与 `card.completion_notify.mention` 提供细粒度控制。字符串布尔值与 profile/bot card override 也通过完整配置加载路径规范化。
- schema 2.0 主卡和 legacy auxiliary interaction 卡都能渲染 mention，但 legacy 卡不会晋升为主卡 PATCH owner。

## 安全边界

- 原 schema 2.0 streaming message 保持唯一 PATCH owner；legacy approval/clarify message 继续走独立 auxiliary rail，避免恢复跨 card dialect 更新与 `230099/200800`。
- 无 anchor 的 topic create 会落在父群而不是原话题；保留话题位置仍要求真实 reply anchor 并使用 reply API。本版本不猜测或反解 `omt_*` 根消息。
- Issue #237 提议的 uncertain-warning 节流不在本版本范围；本轮只修复已确认的非法 create 请求。
- callback authentication、interaction ownership、Hermes patch ownership、delivery UUID 绑定和归档 `legacy/` runtime 未放宽。

## 验证状态

- #237 修复的普通 wheel 隔离全量 pytest：**`3283 passed, 5 skipped`**；PR #238 的 12 项 CI 全绿；exact merge：`199d0390269693e74d1ff130cb7b4ecc4570dcfe`。
- #228 最终组合的相关 unit：**`225 passed`**；完整 server integration：**`324 passed`**；两条新增 completion regression 单独验证：**`2 passed`**；最终 rebased head 的 12 项 CI 全绿；exact merge：`69f47123611bb1639e74d9a076212ce621322805`。
- v4.3.6 release candidate：`git diff --check` **通过**；fresh Python 3.12 normal-wheel 环境完整 pytest **`3325 passed, 5 skipped in 560.94s`**；PEP 517 sdist/wheel、隔离 `site-packages` 中的 package/distribution `4.3.6`、唯一 Hermes plugin entrypoint、24 个 provenance slices，以及主 CLI 与 `enable/disable --help` 均已验证。
- release PR CI、exact release merge、annotated tag、public tagged install 与 Release assets/checksums：**待执行**。
- 真实飞书：Issue #237 报告者已对照验证非法 `thread_id` create 返回 `99992402`，而 `chat_id` create 与 reply API 成功，并报告本地热修后 create 恢复。维护者本轮独立客户端 smoke：**未执行**；自动化结果不冒充平台验收。

## 致谢

感谢 @leavrcn 提供 Issue #237 的生产指标、飞书 API 对照、刷屏链路分析与本地热修验证。

感谢 @Cassius0924 实现 PR #228，并根据多轮审查修复配置总开关、跨 dialect owner 与无 sender completion notification 边界。
