# V3.8.5 版本说明

V3.8.5 是 V3.8.4 WebSocket 命令卡片的反馈补丁。它补齐“始终允许/无需确认”路径：当 Hermes 直接执行 `/new`、`/reset`、`/clear`、`/undo`、`/stop` 或直接 `/model <model>` 后，执行结果也会以 Feishu/Lark interactive card 回复，而不是退回灰色原生文本。

## 主要变化

- **直通命令结果也进卡片**：patcher 现在把当前 `event` 传给 hook runtime，Feishu adapter `send()` 能识别这次输出来自独立 slash command，并把结果包装成命令卡片。
- **`/new` 始终允许体验闭环**：当 `destructive_slash_confirm: false` 或用户已永久允许 `/new` 时，`Session reset`、当前模型、provider、context 等反馈会出现在绿色卡片里。
- **`/model` 反馈稳定卡片化**：模型选择/切换后的结果继续以绿色卡片反馈，避免用户误以为下拉已经执行但没有状态回写。
- **`/update` 保持后台命令**：升级命令仍按 Hermes 原生后台流程运行，不被误包装成交互卡片。
- **移除无效 direct update**：Feishu interactive card 的点击反馈由 callback response 更新，不再额外调用 `message.update(msg_type="interactive")`，避免飞书拒绝 `invalid msg_type`。
- **升级兼容**：安装器可以识别 V3.8.4 生成的旧 command-card hook block，并在重新 `install` 时替换成 V3.8.5 的 `event=event` 版本。

## 升级

```bash
git checkout v3.8.5
pip install -e ".[test]" --upgrade
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
```

Docker 容器内安装示例同步为：

```bash
export HFC_VERSION=v3.8.5
bash install-docker.sh
```

`docker-compose.example.yml` 的默认示例版本已同步为 `v3.8.5`。

## 验证

自动化测试覆盖：

- `/new` 始终允许/无需确认时，Hermes 直通结果以 Feishu interactive card 发送。
- 命令结果上下文只消费一次，后续普通回复不会被误包装成卡片。
- `/update` 仍保留普通文本/后台升级路径。
- Feishu card action 只依赖 callback response 更新，不再调 direct interactive `message.update`。
- V3.8.4 旧 hook block 可被 V3.8.5 patcher 识别并升级。

真实环境验证重点：

- 在飞书/Lark 会话中发送 `/new`，若无需确认，应直接得到绿色“会话已重置”卡片。
- 发送 `/model` 并选择模型，结果应以绿色“模型已更新”卡片反馈。
- `/update` 不应弹出独立交互卡片。

## Release assets

GitHub Release 会包含：

- `hermes-feishu-card-v3.8.5-macos.tar.gz`
- `hermes-feishu-card-v3.8.5-linux.tar.gz`
- `hermes-feishu-card-v3.8.5-windows.zip`
- `hermes-feishu-card-v3.8.5-checksums.txt`
