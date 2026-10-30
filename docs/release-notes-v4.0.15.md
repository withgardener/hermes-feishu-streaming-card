# V4.0.15

V4.0.15 修复 Issue #141，并补上 Hermes 升级后 Gateway hook 可能被覆盖的用户侧保护。

## 工具事件与加载状态

- 工具事件改为紧凑两级时间线：首行显示语义状态、工具名和耗时；参数、结果与失败原因放在第二行小字，不再使用整块 Markdown 引用背景。
- 首个模型或工具事件到达前，同一张卡显示带 spinner 的“正在加载上下文…”；运行中工具继续复用该动画。
- 动画通过既有 `FlushController` 串行 PATCH 同一卡，每 0.8 秒推进一次、最多约 12 秒；正文、工具终态或消息终态到达即停止，不改变 message id、topic 或 reply anchor。
- 成功、运行中、失败、取消和等待保持确定性的语义状态；终态 drain 与原生消息抑制边界不变。

## Hermes 升级保护

- `status` / `start` 从 `--hermes-dir`、选定 env file、配置旁 `.env` 或进程环境解析 `HERMES_DIR`，只读检查 hook 安装状态。
- 对经过验证的 Hermes 升级覆盖，输出 `hook.status: upgrade_repair_required`；`start` 在 sidecar 启动前拒绝继续，并打印显式 `install --accept-hermes-upgrade --yes` 与 `hermes gateway start`。
- 用户编辑、损坏、不受支持或证据不足的状态只输出 `manual_review_required`，不会提供绕过 fail-closed 的升级接受命令。
- 安装器实际改变 Gateway 或 cron source 后，会明确输出 `gateway.restart_required: hermes gateway start`。

## 验证

- 真实 Hermes 配置模型 `deepseek-v4-flash` 在飞书中验证了初始加载 spinner、运行中工具切换和单卡最终收束；投递与更新无失败。
- 升级模拟覆盖：发现 hook 丢失、诊断只读、拒绝静默启动、显式恢复、恢复后 installed，以及用户编辑不提供 acceptance 捷径。
- 完整自动化通过：`1498 passed, 4 skipped`；sdist/wheel 构建、隔离环境 `site-packages` 导入 `4.0.15` 和 CLI smoke 均通过。

## Release assets

- `hermes-feishu-card-v4.0.15-macos.tar.gz`
- `hermes-feishu-card-v4.0.15-linux.tar.gz`
- `hermes-feishu-card-v4.0.15-windows.zip`
- `hermes-feishu-card-v4.0.15-checksums.txt`
