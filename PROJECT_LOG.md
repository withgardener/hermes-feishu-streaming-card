# Hermes Feishu Streaming Card V3.2.1 — 项目日志

> 生成时间：2026-05-01
> 分支：`main`
> 最新 tag：`v3.2.1`
> 状态：✅ 生产就绪

---

## 一句话总结

这是一个**生产就绪**的 sidecar-only 插件，为 Hermes Agent Gateway 提供飞书流式卡片消息功能。采用 AST 安全的代码补丁注入、多 bot 路由、以及强类型事件协议。当前部署在真实 Hermes 环境下，并通过 mock Feishu server、真实 Feishu smoke 测试和 16k+ 中文压力测试验证通过。

---

## 技术栈

- **Python 3.9+**，包构建工具：**setuptools**（`pyproject.toml`）
- 依赖：`aiohttp`、`PyYAML`（可选：`pytest`、`pytest-asyncio`）
- 进程管理：PID 文件、健康检查令牌验证、`os.killpg` 优雅关闭
- Hermes 注入方式：**AST 级别解析** + SHA256 manifest + 原子文件写入 + 自动回滚

---

## 架构：6 层数据流

```
1. Hermes Gateway (run.py)
   └─ 3 个注入点：
      ├─ PATCH_BEGIN: message.started  (进入 _handle_message_with_agent 后)
      ├─ TOOL/THINKING/ANSWER_DELTA:  tool.updated / thinking.delta / answer.delta
      └─ COMPLETE_PATCH_BEGIN: message.completed (在 `return response` 前)
         ↓ fail-open, fire-and-forget
2. hook_runtime.py
   └─ 从 `locals()` 中提取 chat_id/message_id/source/delta 等
   └─ message_id 回退逻辑（SHA256 哈希，生命周期令牌去重）
   └─ 每个 message_id 单调序列号
   ↓ HTTP POST /events
3. server.py (aiohttp 应用)
   └─ SidecarEvent.from_dict() 验证
   └─ 每个 message_id 使用 asyncio.Lock 串行化
   └─ 路由解析（多 bot）→ 创建/发送/更新 Feishu 卡片
   ↓ BotRegistry.resolve(RoutingContext)
4. feishu_client.py
   └─ 租户令牌缓存（到期时间 = expire - 60 秒）
   └─ IM API: POST /messages（发送），PATCH /messages/{id}（更新）
   └─ Accept-Encoding: gzip, deflate（V3.2.1 修复 brotli）
   ↓ Feishu IM/CardKit API
5. session.py + render.py
   └─ CardSession：thinking_text / answer_text / tools / tokens / context
   └─ render_card()：分块 2400 字符 Markdown 元素，footer（duration/model/tokens/context）
   ↓
6. 飞书卡片（打字机效果）
```

---

## 源代码文件（hermes_feishu_card/）

| 文件 | 行数 | 职责 |
|---|---|---|
| `server.py` | 410 | aiohttp 应用，事件处理管道，bot 路由，更新节流 |
| `cli.py` | 1033 | 9 个子命令（doctor/setup/install/restore/uninstall/start/stop/status/bots/smoke-feishu-card）|
| `hook_runtime.py` | 618 | 注入到 Hermes 的运行时 — 从 locals() 提取事件，message_id 回退，序列号 |
| `install/patcher.py` | 848 | AST 级别代码注入器 — 找到 handler 主体，插入标记块，验证完整性 |
| `install/detect.py` | 283 | Hermes 版本/结构检测 — AST 遍历器查找 `hooks.emit("agent:end")` |
| `install/manifest.py` | 12 | 文件 SHA256 计算器 |
| `bots.py` | 197 | BotRegistry + RoutingContext + FeishuClientFactory |
| `config.py` | 98 | 配置加载，默认值合并，环境变量覆盖，端口验证 |
| `events.py` | 90 | SidecarEvent 数据类 + 验证（9 个必填字段，6 种事件类型）|
| `feishu_client.py` | 183 | Feishu API HTTP 客户端 — 令牌缓存，send_card，update_card_message |
| `render.py` | 155 | 卡片 JSON 构建器 — 状态相关 header，分块 body，可配置 footer |
| `session.py` | 95 | CardSession — 事件应用，思考/答案缓冲，ToolState |
| `runner.py` | 131 | 入口点 — 构建 FeishuBoundary，web.run_app |
| `text.py` | 59 | 流式文本规范化 — 过滤 `<think>` 跨块拆分，刷新判断逻辑 |
| `metrics.py` | 21 | SidecarMetrics 数据类（12 个计数器）|
| `process.py` | 188 | Sidecar 生命周期管理 — start/stop/status/health 检查，PID 文件 |

---

## 事件协议（6 种类型）

| 事件 | 数据 | 触发位置 |
|---|---|---|
| `message.started` | chat_type, tenant_key, agent_id, profile_id（可选）| handler 入口 |
| `thinking.delta` | text（增量）| _interim_assistant_cb |
| `answer.delta` | text（增量）| _stream_delta_cb |
| `tool.updated` | tool_id, name, status, detail | progress_callback |
| `message.completed` | answer, duration, model, tokens, context | 在 `return response` 之前 |
| `message.failed` | error | 由 gateway 自定义（如果适用）|

---

## Patch 注入系统

打了 **5 个 patch** 到 `gateway/run.py`：

1. **`PATCH_BEGIN/END`**：`emit_from_hermes_locals(locals())` → message.started
2. **`COMPLETE_PATCH_BEGIN/END`**：`await emit_from_hermes_locals_async({...answer/duration/tokens...})` → message.completed，返回 None 以抑制重复文本消息
3. **`TOOL_PATCH_BEGIN/END`**：tool.updated（仅当 `event_type in ("tool.started", "tool.completed")` 时）
4. **`ANSWER_DELTA_PATCH_BEGIN/END`**：answer.delta（流式增量）
5. **`THINKING_DELTA_PATCH_BEGIN/END`**：thinking.delta（尚未流式的 thinking 内容）

所有 patch 都具有：
- **防腐蚀完整性**：如果任何标记损坏 → `ValueError("corrupt patch markers")`
- **原子回滚**：安装失败时移除所有备份/manifest 文件
- **修改保护**：如果原始 run.py 更改，恢复/卸载拒绝覆盖

---

## 配置层级（优先级从低到高）

1. `hermes_feishu_card/config.py` 中的默认值
2. 用户 YAML（默认：`~/.hermes_feishu_card/config.yaml`）
3. 环境变量：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`HERMES_FEISHU_CARD_HOST`、`HERMES_FEISHU_CARD_PORT`、`HERMES_FEISHU_CARD_ENABLED`、`HERMES_FEISHU_CARD_EVENT_URL`、`HERMES_FEISHU_CARD_TIMEOUT_MS`

---

## 测试覆盖范围：398 个测试

- `tests/unit/`：config、bots、events、session、render、text、hook_runtime、feishu_client、patcher
- `tests/integration/`：服务器生命周期、E2E 事件流、CLI 进程、feishu_client HTTP
- `tests/integration_test.py`：单体测试入口

---

## 关键改进（V3.2.x）

- **V3.2.0**：多 bot 注册，chat_id→bot_id 路由，bots CLI，`/health.routing` 诊断，群聊规则框架（预留）
- **V3.2.1**：`Accept-Encoding: gzip, deflate` 修复 brotli 解码错误

---

## 约束与已知问题

- Hermes 必须 ≥ `v2026.4.23`
- `gateway/run.py` 不能是符号链接
- 卡表格限制 ≥ 5（Issue #10，未处理，仅 FAQ）
- `bindings.group_rules.enabled` 目前为 `false`（预留）
- 非 terminal 事件的更新节流（最小 2 秒间隔）
- Sidecar 通过 PID 文件 + 进程令牌健康检查进行自我管理

---

## 从 V2 到 V3.2.1 的变化

| V2.x（hermes-feishu-streaming-card/） | V3.2.1（hermes-feishu-streaming-card-git/） |
|---|---|
| 扁平 Python 文件，单独脚本 | 包结构（`hermes_feishu_card/`），pip 可安装 |
| 手动 `python installer_v2.py --mode sidecar` | `hermes-feishu-card setup --hermes-dir ... --yes` |
| 基于正则表达式、脆弱的 patch 注入 | AST 解析，签名标记块，SHA256 manifest |
| 单 bot | 多 bot + chat_id 路由 |
| 事件：扁平 `{event, data}` | 强类型 `SidecarEvent` 数据类，`message.*` 语义 |
| 过时的 legacy/dual 模式 | Sidecar-only |
| 简陋的进程管理 | PID 文件 + 令牌验证 + 优雅的 SIGTERM/SIGKILL |
| ~50 个测试 | 398 个 pytest 测试 |

---

## 版本历史

| 版本 | 日期 | 类型 | 说明 | Tag |
|------|------|------|------|-----|
| V3.2.1 | 2026-04-29 | Patch | 修复 brotli 解码错误（Accept-Encoding header） | `v3.2.1` |
| V3.2.0 | 2026-04-29 | Feature | 多 bot 路由、群聊绑定、CLI 管理、routing diagnostics | `v3.2.0` |
| V3.1.0 | 2026-04-XX | Feature | sidecar-only 架构首次发布 | `v3.1.0` |

---

## 部署检查清单

```bash
# 安装
git clone https://github.com/baileyh8/hermes-feishu-streaming-card.git
cd hermes-feishu-streaming-card
python3 -m pip install -e ".[test]"
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes

# 验证
curl http://127.0.0.1:8765/health | jq '.routing'
python3 -m hermes_feishu_card.cli doctor --config ~/.hermes_feishu_card/config.yaml
python3 -m hermes_feishu_card.cli bots list --config ~/.hermes_feishu_card/config.yaml
```

---

*项目日志由 AI 助手自动生成，基于 V3.2.1 代码库完整审查。*
