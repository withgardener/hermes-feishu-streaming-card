# V3.8.3 版本说明

V3.8.3 是 V3.8 系列的命令交互补丁。它延续 V3.8.0 的主回答/辅助 timeline 布局、V3.8.1 的高频 delta 合并和 V3.8.2 的 timeline 阅读体验，这一版重点补齐 Hermes slash 命令在飞书里的交互卡片体验。

## 主要变化

- **独立 slash 确认卡片**：`/new`、`/reset`、`/undo`、`/model <model>` 等 Hermes 需要确认的独立命令，会优先通过 Feishu sidecar 发出一张独立命令卡片。
- **同卡片更新结果**：用户点击命令卡片选项后，插件调用 Hermes 原始 handler，并把执行结果更新回同一张命令卡片。
- **`/model` 选择卡片**：当 Hermes 请求 Feishu adapter 的 `send_model_picker(...)` 时，插件会补上 Feishu-only 模型选择卡片，选择后调用 Hermes 的模型切换 callback。
- **职责边界更清楚**：正在运行的 Agent 卡片继续承接 approval、clarify、对话选项和思考/工具 timeline；`/new`、`/reset`、`/model` 这类独立命令不会混入上一张 Agent 卡片。
- **`/update` 不弹交互卡片**：`/update` 保持 Hermes 后台升级命令语义，不做按钮式确认卡片。
- **保留文本 fallback**：sidecar 不可用、卡片应用失败、用户选择超时或命令卡片完成态更新失败时，继续交给 Hermes 原生文本路径，避免命令卡死或结果丢失。本机/私有 sidecar 降级到 `interaction_mode=text` 时，不会先制造一张残留命令卡片。

## 升级

```bash
git checkout v3.8.3
pip install -e ".[test]" --upgrade
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes
```

Docker 容器内安装示例同步为：

```bash
export HFC_VERSION=v3.8.3
bash install-docker.sh
```

`docker-compose.example.yml` 的默认示例版本已同步为 `v3.8.3`。

## 验证

自动化测试覆盖：

- async slash confirmation card request / poll / choice。
- `/model` picker card callback 与同卡片完成态更新。
- command-card `message.completed` 事件。
- text-mode native fallback 不应用命令卡片，避免“残留卡片 + 灰色原生提示”重复。
- Hermes `gateway/run.py` patcher 的插入、幂等和移除。
- 完成态更新失败时回退 Hermes 原生文本路径。

真实环境 smoke：

- 本机 Hermes + 当前飞书 bot 已验证私有 `interaction_mode=text` 边界：`/new` 只返回 Hermes 原生确认文本，`/cancel` 可正常取消；`/model` 只返回 Hermes 原生模型列表；两者都没有额外生成残留 sidecar 命令卡片。
- 独立命令卡片的按钮闭环通过 mock sidecar / pytest 覆盖：slash confirm、`/model` picker、card action poll、同卡片完成态更新和失败 fallback。
- 公网 callback 模式下的真实按钮点击验收可作为后续实机验收项；V3.8.3 不改变 `/update`，避免触发后台升级命令的交互卡片。

## Release assets

GitHub Release 会包含：

- `hermes-feishu-card-v3.8.3-macos.tar.gz`
- `hermes-feishu-card-v3.8.3-linux.tar.gz`
- `hermes-feishu-card-v3.8.3-windows.zip`
- `hermes-feishu-card-v3.8.3-checksums.txt`
