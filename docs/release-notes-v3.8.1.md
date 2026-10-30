# V3.8.1 版本说明

V3.8.1 是 V3.8 系列的稳定性补丁，重点修复 issue #74：Hermes Agent 0.17.0+ 在 thinking model、长上下文和高频 streaming delta 场景下，启用飞书流式卡片插件可能触发 `Stream stale for 180s`。这一版把 delta 合并前移到 Hermes Gateway 进程内，减少 hook 热路径压力，同时补上飞书内只读诊断命令。

## 核心修复

- **issue #74 高频 delta 堵塞修复**：`thinking.delta` / `answer.delta` 不再逐 token 直接排队发送 HTTP 事件，而是在 Gateway runtime 内按时间窗口和字符数合并后再发给 sidecar。
- **终态前 flush pending delta**：`message.completed` / `message.failed` 前会先 flush 同一消息 pending delta，避免最终卡片丢失尾部内容。
- **兼容旧 hook 升级/卸载**：patcher 能识别 V3.8.0 及更早已安装的无命令 hook block，并升级为 V3.8.1 新 block。

## 飞书内只读诊断

新增 `/hfc` 命令入口，命令结果会以飞书卡片回复当前消息，不执行写操作：

- `/hfc help`：查看命令列表。
- `/hfc status`：查看 sidecar、active session、基础发送和事件指标。
- `/hfc doctor`：查看路由、更新错误和 bot 绑定摘要。
- `/hfc monitor`：查看流式更新、coalescing、terminal drain 和飞书发送/更新指标。

诊断卡片只展示 hash 后的 `chat_id` / `message_id` / `thread_id` 上下文。`/messages/{message_id}/summary` 也改为返回 hash 字段，不再回显 raw `chat_id` 或 Feishu `message_id`。

## 新增环境变量

默认配置适合大多数场景，无需手动设置：

```bash
export HERMES_FEISHU_CARD_DELTA_COALESCE_MS=250
export HERMES_FEISHU_CARD_DELTA_COALESCE_CHARS=600
export HERMES_FEISHU_CARD_DELTA_COALESCE_MAX_PENDING=128
```

如果希望更快刷新，可降低 `HERMES_FEISHU_CARD_DELTA_COALESCE_MS`；如果仍遇到极端高频 thinking burst，可适当提高 `HERMES_FEISHU_CARD_DELTA_COALESCE_CHARS`。

## 升级

```bash
git checkout v3.8.1
pip install -e ".[test]" --upgrade
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli stop --config ~/.hermes/config.yaml
python3 -m hermes_feishu_card.cli start --config ~/.hermes/config.yaml
```

Docker 容器内安装/更新：

```bash
export HFC_VERSION=v3.8.1
bash install-docker.sh
```

`docker-compose.example.yml` 的默认示例版本已同步为 `v3.8.1`。

## 验证

本次发布覆盖：

- 高频 `answer.delta` 合并回归测试。
- terminal event 前 pending delta flush 回归测试。
- `/hfc` hook 命令拦截和 sidecar command card 测试。
- V3.8.0 旧 hook block 升级/卸载兼容测试。
- summary raw id 脱敏测试。

Release assets:

- `hermes-feishu-card-v3.8.1-macos.tar.gz`
- `hermes-feishu-card-v3.8.1-linux.tar.gz`
- `hermes-feishu-card-v3.8.1-windows.zip`
- `hermes-feishu-card-v3.8.1-checksums.txt`
