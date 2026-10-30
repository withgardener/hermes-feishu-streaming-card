# V3.8.1 设计方案：高频 Delta 稳定性修复与只读诊断命令

## 背景

V3.8.0 已完成卡片主回答区与 reasoning / tool timeline 分离、terminal drain、长 Markdown 安全切分和 Docker 示例同步。发布后 open issue #74 报告：在 Hermes Agent 0.17.0、Qwen3-Max thinking mode、长上下文和高频 streaming delta 场景下，启用插件会触发 `Stream stale for 180s — no chunks received`，并阻塞其它并发会话；禁用插件后问题消失。

同时，V3.8 路线中原计划 V3.8.1 提供飞书内运维命令。为了兼顾稳定性与可观测性，V3.8.1 调整为一个小而明确的版本：

- 必须修复 #74 的 Gateway 热路径压力。
- 只提供只读 `/hfc` 诊断命令。
- 不提供 reload、continue、retry、cancel 等写操作或会话控制。

## 目标

1. 高频 `thinking.delta` / `answer.delta` 不再每 token 都执行完整 `build_event + run_coroutine_threadsafe + ordered POST`。
2. `message.completed` / `message.failed` 前必须 flush 同一 message 的 pending delta，保证终态卡片不丢内容。
3. `/hfc help`、`/hfc status`、`/hfc doctor`、`/hfc monitor` 在进入 LLM 前被插件处理，并返回飞书卡片。
4. 只读命令响应必须脱敏，不暴露 Feishu token、app secret、raw chat_id、raw Feishu message_id。
5. 版本号、README、CHANGELOG、release notes 和 TODO 同步到 V3.8.1。

## 非目标

- 不做 `/hfc reload`。
- 不做继续、重试、取消按钮。
- 不控制 Hermes 正在运行的会话。
- 不发布官方 Docker 镜像。
- 不把 sidecar `/health` 的全部原始 JSON 直接暴露给飞书用户。

## #74 根因假设与修复边界

现有 sidecar 已经有 PATCH 合并和 terminal drain，但 #74 的症状发生在 Hermes gateway 读取模型流时。当前 hook 的热路径是：

`thinking.delta/answer.delta` 每次触发 -> `emit_from_hermes_locals_threadsafe()` -> `build_event()` -> `_event_data()` -> `run_coroutine_threadsafe()` -> `_post_json_ordered()` -> executor POST sidecar。

对于 thinking 模型的 token-by-token delta，这会在 Hermes stream-reader daemon thread 上产生大量 Python 对象构造、锁、future 调度和 GIL 竞争。V3.8.1 的修复点必须前移到 `hook_runtime.py`，在 gateway 进程内先把 delta 合并成较少事件，再交给 sidecar。

## Gateway-Side Delta 合并设计

### 触发范围

只合并：

- `thinking.delta`
- `answer.delta`

不合并：

- `message.started`
- `tool.updated`
- `interaction.*`
- `message.completed`
- `message.failed`
- cron delivery

### 合并键

合并键由以下字段组成：

- event URL
- Hermes event loop identity
- profile id
- message id
- event name

不同 message、不同 profile、不同 event type 必须互相隔离。

### 发送策略

新增 runtime 配置：

- `HERMES_FEISHU_CARD_DELTA_COALESCE_MS`，默认 `250`，范围 `0..5000`。
- `HERMES_FEISHU_CARD_DELTA_COALESCE_CHARS`，默认 `600`，范围 `1..20000`。
- `HERMES_FEISHU_CARD_DELTA_COALESCE_MAX_PENDING`，默认 `128`，范围 `1..5000`。

行为：

1. delta 到达时，只构建合并 key 所需的最小 identity，不立即构建完整 sidecar payload。
2. 将文本追加到 pending buffer。
3. 如果 pending 字符数达到阈值，立即 flush。
4. 否则在指定时间窗口后由 Hermes loop 执行 flush。
5. `message.completed` / `message.failed` 到达前，同步 flush 同一 message 的 pending delta。
6. disabled 或合并窗口为 0 时，保留旧行为，便于排障。

### 顺序保证

- 每个 flush 仍使用原有 `_post_json_ordered_response()` / `_post_json_ordered()`，保留 per-message 顺序。
- terminal 事件前先 flush pending delta，再发送 terminal。
- flush 生成的合并 delta 使用 `_next_sequence(message_id)`，terminal 继续按原逻辑递增。

### 失败策略

- delta flush 失败仍 fail-open，不影响 Hermes 原生流。
- terminal flush 失败不阻塞 terminal 发送。
- pending buffer 超过 max pending key 时，丢弃最旧的非 terminal pending 项，并记录 runtime warning 计数。

## 只读 `/hfc` 命令设计

### 命令识别

hook 在 message started 阶段前或最早可拿到用户文本的位置识别：

- `/hfc`
- `/hfc help`
- `/hfc status`
- `/hfc doctor`
- `/hfc monitor`

识别条件：

- platform 必须是 Feishu。
- 文本必须以 `/hfc` 开头，大小写不敏感。
- 不识别普通消息中间的 `/hfc`。

识别成功后，插件处理命令并返回 `True` 给 patcher，使 Hermes 不进入 LLM。

### 响应位置

命令响应使用飞书卡片发送到当前 chat/thread：

- 私聊：发到当前 chat。
- thread：优先 reply 到当前 thread。
- 群聊：发到当前 chat；后续 @机器人触发策略不在本版实现。

### 命令数据源

sidecar 新增只读命令端点：

- `POST /commands`

请求字段：

- `command`
- `chat_id`
- `message_id`
- `thread_id`
- `reply_to_message_id`
- `profile_id`
- `created_at`

响应字段：

- `ok`
- `handled`
- `title`
- `status`
- `lines`
- `metrics`

hook 只负责识别和转发，不在 gateway 内重复实现 doctor/monitor 逻辑。

### 命令内容

`/hfc help`：

- 展示四个命令和用途。

`/hfc status`：

- plugin version
- sidecar status
- active sessions
- bot/profile routing 摘要
- recent route error

`/hfc doctor`：

- config 是否加载
- sidecar 是否可达
- runtime import 状态摘要
- hook/streaming 建议摘要
- 不执行会修改系统的 repair/install。

`/hfc monitor`：

- `events_received`
- `events_applied`
- `events_rejected`
- `update_scheduled`
- `update_coalesced`
- `update_queue_peak`
- `terminal_drains`
- `terminal_drain_timeouts`
- `feishu_update_latency_ms`
- recent update/route error 摘要

## 安全与脱敏

- 所有返回给飞书的诊断字段走 allowlist。
- raw `chat_id`、raw `message_id`、token、secret、authorization、tenant token 不进入卡片正文。
- 需要标识时使用短 hash，例如 `hash:abcd1234`。
- sidecar `/messages/{message_id}/summary` 中的 `chat_id` 和 `message_id` 同步脱敏或移除，补齐 TODO 中的安全清理。

## 测试策略

### #74 回归测试

- 1000 个 `answer.delta` 只应触发少量 sidecar POST。
- 1000 个 `thinking.delta` 只应触发少量 sidecar POST。
- terminal event 前 flush pending delta，最终 POST 顺序为 delta 在前、terminal 在后。
- 不同 message id 的 delta 不互相合并。
- coalescing disabled 时保持旧行为。

### `/hfc` 命令测试

- `/hfc help/status/doctor/monitor` 被识别为命令，不进入普通 `message.started`。
- 命令请求能携带 chat/thread/reply context。
- sidecar `/commands` 返回飞书卡片并应用到当前 chat。
- 命令响应不包含 raw secret、raw chat_id、raw message_id。
- 未知命令返回 help。

### 文档与发布测试

- README / README.en 包含 V3.8.1 说明。
- CHANGELOG 包含 V3.8.1。
- release notes 包含 #74 和 `/hfc` 只读命令。
- TODO 标记 V3.8.1 已完成，写操作顺延。

## 验收标准

- #74 有明确失败测试和修复。
- `/hfc help/status/doctor/monitor` 有单元测试和 integration-level sidecar 测试。
- 相关 pytest 通过，全量 pytest 通过。
- `pyproject.toml` 版本为 `3.8.1`。
- 创建 `v3.8.1` tag 和 GitHub Release。
- 回复 issue #74，说明修复策略和升级方式。
