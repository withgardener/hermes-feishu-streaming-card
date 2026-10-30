# 事件协议

[中文](event-protocol.md) | [English](event-protocol.en.md)

Hermes 最小 hook 向 sidecar 发送消息生命周期事件。第二阶段 hook runtime 会把可识别的 Hermes 消息上下文组装为 `SidecarEvent` JSON，并 fail-open 发送到本机 sidecar `/events`。sidecar 只依赖事件语义，不把飞书卡片逻辑放回 Hermes 进程。

## 事件列表

| 事件 | 说明 |
| --- | --- |
| `message.started` | 新消息开始，sidecar 创建或初始化会话卡片。 |
| `thinking.delta` | 模型思考内容增量。sidecar 累积显示思考内容。 |
| `tool.updated` | 工具调用状态变化。sidecar 在卡片内实时显示工具调用次数。 |
| `answer.delta` | 最终答案增量。sidecar 累积答案内容，等待完成事件落最终态。 |
| `message.completed` | 消息正常完成。卡片状态切换为 `已完成`，最终答案覆盖思考内容。 |
| `message.failed` | 消息失败。卡片结束当前流式更新，并展示可公开的失败状态或摘要。 |
| `interaction.requested` | Hermes 需要用户授权或选择时发出。sidecar 在同一张卡片中渲染按钮或编号文本选项，并在 `/interactions/{interaction_id}` 暴露等待状态。响应会带 `interaction_mode`，`text` 模式下 hook 会立即交还 Hermes 原生文本交互流程。 |
| `interaction.completed` | 用户点击卡片按钮后发出。sidecar 更新原卡片为已选择状态，并让 Hermes hook 轮询到选择结果后继续执行。 |
| `interaction.failed` | 交互请求失败或超时。sidecar 保留失败状态，Hermes hook 可 fail-open 回到原生 Hermes 交互路径。 |

`interaction.requested.data.allow_custom_input` 明确声明当前交互是否允许用户输入选项之外的内容。为 `true` 时卡片显示“其他”输入框；为 `false` 时只显示 Hermes 下发的固定选项。hook 对 Clarify 交互下发 `true`，对审批交互默认下发 `false`，因此审批卡片与 Hermes 原生 UI 保持一致。兼容旧事件时，仅 `kind=clarify` 会默认允许自定义输入。

## 路由字段

所有事件都保留 `conversation_id`、`message_id` 和 `chat_id` 三个必填字段。V3.6.4 起，事件还可以携带可选 `thread_id` 字段；当它是飞书 `om_` / `omt_` thread 上下文时，sidecar 会在创建初始卡片时使用飞书 reply API，把卡片发回用户所在的同一 thread。后续更新仍然 PATCH 这条已创建的卡片消息。

当 Hermes 只有“从当前消息创建 thread”的意图、尚未拿到 `thread_id` 时，hook 可以同时发送 `data.reply_in_thread=true` 与 `data.reply_to_message_id`。sidecar 会把该意图保存在当前 `CardSession`，因此后续 approval/clarify 交互卡以及 runtime-admission 延迟投递仍使用同一 reply API 和锚点，不会回落到群聊顶层。

`turn_id` 是可选字段，用来稳定标识一次 Agent turn；`message_id` 保留当前事件、stream 或 reply identity，`data.reply_to_message_id` 只表示飞书回复锚点。当 `turn_id` 存在时，session ownership、事件排序、delivery policy 和 native handoff 都使用 `turn_id`，不会通过 `reply_to_message_id` alias 改写所属 turn。

缺少 `turn_id` 时，sidecar 保持兼容：以 `message_id` 作为 turn identity，并继续允许后续 stream 事件通过 `reply_to_message_id` alias 路由到已有 active session。

## 卡片状态

卡片正常状态只有两个：

- `思考中`
- `等待选择`
- `已完成`

`思考中` 阶段显示累积的 `thinking.delta` 内容，并在同一张卡片内实时更新工具调用次数。`interaction.requested` 到达后，卡片进入 `等待选择`。默认 `auto` 模式通过 Hermes Feishu adapter 的 WebSocket 原生 card-action channel 接收按钮点击，再转发到 sidecar `/card/actions`，因此 localhost/private sidecar 不需要公网 callback URL；只有显式配置 `text` 时才显示编号选项并交还 Hermes 原生文本交互。V3.8.5 起，`/new`、`/reset`、`/model` 等独立命令也优先走同一条 Feishu/Lark WebSocket 原生 card action 路径，且直通执行结果保持卡片反馈。`message.completed` 后，卡片进入 `已完成`，最终答案替换思考内容；用户不需要在完成态继续看到完整思考轨迹。

## V4.1 控制协议与域分隔

V4.1 在 `/events` 数据面外增加相互隔离的本机控制面，各动作不得复用签名 domain：

| 端点 | 用途 | 签名域 | 失败行为 |
|---|---|---|---|
| `POST /events` | 消息生命周期与卡片数据面 | event domain | 未确认接管时 Hermes 原生 fail-open |
| `POST /delivery/policy` | 在 hook 抑制原生消息前查询 per-chat 决策 | `hfc-policy-v1` | timeout、invalid/replayed proof、配置错误或未知 profile 都返回原生路径 |
| `POST /runtime/events` | `runtime.hello` / `runtime.heartbeat` readiness | `hfc-runtime-v1` | Hermes 工作继续；sidecar readiness 降级，不授权源码 mutation |
| `POST /native-handoff/recover` | 用 obligation/content/plan/target hash 与 canonical route 精确查询 pending native descriptor | `hfc-native-handoff-recovery-v2` | 任一 fence 不匹配都返回未找到；Hermes 保留 recovered marker 与随机 UUID fail-open |
| `POST /native-handoff/ack` | 全部分片成功且 ledger 已 `delivered` 后确认 native final | `hfc-native-handoff-ack-v1` | ACK 失败不回滚已 delivered ledger；sidecar pending 最终转 uncertain |

policy、runtime、native recovery 与 native ACK proof 都绑定 exact raw body、短 timestamp window 与 nonce replay protection。recovery body 只携带 64 位 obligation/content/plan/target digest 和 `create` / `thread-create` 枚举，不携带答案正文或 reply anchor；响应不回显 chat id、transport root、路径、源码 hash 或 recovery fingerprint。`runtime.hello` / `runtime.heartbeat` 只提供经过 schema 限制的 generation/package/sequence 信息；严格 repair 仍独立验证 Git、manifest、backup、blob、anchor 与 mutation 前 fingerprint。

exact native handoff 还要求 Gateway 与 sidecar 同时声明 `native-ack-v2`、`stable-feishu-uuid-v2`、`exact-base-delivery-v1`，descriptor protocol 必须是 `hfc-native-handoff-v2`。terminal POST 响应丢失或损坏时，Gateway 立即用相同 obligation/content/plan/route/target 五项 binding 发起 recovery-v2 查询；若查询也不可用，本轮可使用同五项派生的 provisional UUID seed，随后只在取回完整 descriptor 后 ACK。若最初请求没有到达 sidecar，后续仍保持带可见 marker 的普通 native fail-open，不把不确定结果冒充成 exact 成功。该契约只覆盖默认 profile、无附件/媒体的 Hermes 0.19 Base 普通文本 final-answer；secondary profile 不广告 exact ACK。

一个 turn 的 delivery decision 在首次事件时固定。`bindings.native_chats` 的修改只影响下一条新消息；重复 terminal 不能在卡片与原生路径各发送一次。sidecar 在创建 `CardSession` 前再次检查 policy，因此 hook preflight 与 server enforcement 缺一不可。

## 内容安全

sidecar 必须过滤模型内部思考边界，不得向卡片泄露 `</think>` 标签或类似控制标记。最终答案应来自对外可见的回答内容，而不是原始内部流。

当前协议和卡片行为通过 fake client、fixture Hermes、mock sidecar、Feishu callback 模拟和真实 Feishu smoke 测试守卫。
