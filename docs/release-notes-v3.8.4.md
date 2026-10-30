# V3.8.4 版本说明

V3.8.4 是 V3.8.3 独立命令卡片的 WebSocket 热修。它修正本地/private sidecar 部署下 `/new`、`/reset`、`/undo`、`/model` 仍然只出现 Hermes 灰色原生文本的问题：Feishu/Lark 机器人本来就是通过 WebSocket 长连接接收卡片点击事件，这一版直接复用 Hermes Feishu adapter 的原生 card action 通道。

## 主要变化

- **Feishu WebSocket 原生命令卡片**：动态补上 Feishu adapter 的 `send_slash_confirm(...)`，`/new`、`/reset`、`/undo` 等确认命令会发送原生 interactive card。
- **按钮点击回到 Hermes 原 handler**：插件包装 `_on_card_action_trigger`，只处理 `hfc_action`，并通过 `tools.slash_confirm.resolve(...)` 调用 Hermes 原本的确认 handler。
- **`/model` 原生选择卡片**：`/model` 无参数选择器在 WebSocket 场景下发送 Feishu interactive card，点击后执行 Hermes 原 `on_model_selected` callback，并把结果写回同一张卡片。
- **避免重复选择卡**：当 Feishu WebSocket 原生卡片可用时，slash confirm 不再先发送 sidecar `interaction.requested` 选择卡，避免 `/new` 同时出现两张选项卡。
- **热升级更稳**：安装逻辑会修复旧进程类上残留的 `_hfc_command_card_methods_installed` 标记，确保 `send_slash_confirm(...)` 真实存在；原生发送失败时会写本地 warning，方便排查。
- **不破坏既有卡片按钮**：Hermes 原有 approval/update 卡片 action 继续走 Feishu adapter 原始逻辑。
- **继续保留 fallback**：Feishu 原生卡片不可用、sidecar 不可用、回调失败或超时时，仍交回 Hermes 原生文本路径。

## 升级

```bash
git checkout v3.8.4
pip install -e ".[test]" --upgrade
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes
```

Docker 容器内安装示例同步为：

```bash
export HFC_VERSION=v3.8.4
bash install-docker.sh
```

`docker-compose.example.yml` 的默认示例版本已同步为 `v3.8.4`。

## 验证

自动化测试覆盖：

- Feishu native `send_slash_confirm(...)` 卡片发送。
- Feishu WebSocket 原生卡片可用时跳过 sidecar 预交互，避免重复选择卡。
- stale install marker 修复，避免热升级后 `send_slash_confirm(...)` 仍缺失。
- Feishu WebSocket card action 点击后调用 `tools.slash_confirm.resolve(...)`。
- Feishu native `/model` picker 卡片发送。
- `/model` picker action 点击后调用 Hermes 原 `on_model_selected` callback。
- V3.8.3 sidecar command-card fallback、text-mode fallback 和 `message.completed` 完成态路径保持可用。

真实环境验证重点：

- 在飞书/Lark 会话中发送 `/new`，应出现独立确认卡片，而不是灰色文本 fallback。
- 点击“允许一次”后，原卡片应更新为已允许/已执行结果。
- 发送 `/model`，应出现独立模型选择卡片；点击模型后，原卡片更新为模型切换结果。
- `/update` 仍不弹交互卡片，继续由 Hermes 后台升级流程处理。

## Release assets

GitHub Release 会包含：

- `hermes-feishu-card-v3.8.4-macos.tar.gz`
- `hermes-feishu-card-v3.8.4-linux.tar.gz`
- `hermes-feishu-card-v3.8.4-windows.zip`
- `hermes-feishu-card-v3.8.4-checksums.txt`
