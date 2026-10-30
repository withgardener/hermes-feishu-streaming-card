# Hermes Feishu Streaming Card V4.4.0

[中文](release-notes-v4.4.0.md) | [English](release-notes-v4.4.0.en.md)

V4.4.0 是一次基于新版 Hermes 的体验与功能升级：飞书中的 `/commands` 从分页文本变为动态原生能力中心，常用 Hermes 命令获得分类浏览、安全快捷入口和 KPI 可视化；流式 backlog 与极端 Markdown 的诊断和兜底也同步加强。

## 新版 Hermes 基线

- 正式兼容基线：Hermes Agent `v2026.8.27` / `0.20.6`。
- 向前兼容验证：Hermes `main@4f22543509d1b91dc45bcb369447126c5eb14fb7`（2026-08-30）。
- 直接读取新版 `hermes_cli.commands.COMMAND_REGISTRY`，包括 category、alias、args hint、subcommands、argument mode、busy policy 与 gateway availability。
- 自动识别新版 `/bg`、`/btw`、`/plan`、Gateway `/busy`，以及运行时 plugin/skill commands，不在 HFC 中复制固定 allowlist。

## Hermes 原生能力中心

- `/commands` 卡片提供首页、分类和命令详情三层视图。
- 首页显示当前 Hermes 原生命令数，并提供状态、上下文、用量、任务、会话和模型等快捷入口。
- 分类页展示完整用法和说明；详情页展示 alias、subcommand、argument mode、busy policy 与命令来源。
- Hermes registry、plugin 或 skill discovery 不可用时 fail-open，保留原 `/commands` 文本反馈。

## 安全命令交互

- `/status`、`/context`、`/usage`、`/agents`、`/sessions`、`/profile`、`/version` 与已有 `/model`、`/resume` 原生 picker 可以从卡片快捷启动。
- 快捷动作复制原 `MessageEvent` 后重新进入 Feishu adapter；Hermes 的 access control、busy policy、plugin hooks、session ownership 与 original handler 继续生效。
- 群聊 callback 绑定原发起人并继续经过 Hermes group admission。
- `/update`、`/new`、`/stop`、`/undo`、`/pause`、`/yolo` 等状态变更命令不提供一键执行；需要参数的命令要求用户在消息框发送完整命令。

## 可视化与运行指标

- `/status`、`/context`、`/usage`、`/agents`、`/sessions`、`/profile`、`/reasoning` 等结果会把稳定的 `Label: Value` 字段提升为 KPI columns。
- 完整 Hermes 原文继续显示在卡片中；识别失败时只显示原文，不因可视化丢字段。
- `FlushController.pending_count` 与 `update_queue_peak` 现在记录一次 PATCH 执行期间实际合并的更新数，不再只报告 0/1。

## Markdown 可靠性

- 普通长表格继续按行拆分并重复表头；单个超长单元格继续拆成结构完整的续行。
- 表头本身超过单块预算时，用明确安全折叠提示替代超限 block。
- 行的列框架无法容纳任何合法续行时，用明确安全折叠提示替代字符级 plain split。
- 五表格 `compact` / `truncate`、200 tagged element、28,000-byte card JSON budget 与 terminal native-answer handoff 保持不变。

## 验证状态

- 动态 registry、能力中心结构、安全 copied-event dispatch、状态变更命令拒绝、KPI 原文保留、真实 backlog depth 与极端表格的聚焦回归已完成。
- 已对独立检出的 Hermes 最新 main 实际加载命令目录，确认识别 66 个 gateway 命令，并读取 `/bg`、`/btw`、`/plan`、`/model`、`/busy`、`/commands` 的新版元数据。
- 完整 pytest：**`3356 passed, 5 skipped`**；`git diff --check`：**通过**。
- sdist/wheel：**构建通过**；干净 Python 3.12 venv 从 wheel 导入 package/distribution version 均为 `4.4.0`，来源为隔离 `site-packages`，CLI entry point 与 `--help`：**通过**。
- release PR CI、exact merge、annotated tag、public install 与 Release assets/checksums 只在发布流程实际完成后记录。
- 真实飞书私聊/群聊 smoke：**已通过（2026-08-31）**。候选 wheel `4.4.0` 运行在官方 Hermes `v2026.8.27` / `0.20.6` 隔离 CLI 环境；私聊和群聊均验证 `/commands` 首页、分类、`/model` 详情、返回导航与安全 `/status` 快捷动作，私聊 `/context` 验证空态和真实用量视图，普通私聊/群聊流式卡均正常完成并显示 footer。
- 验收后 sidecar 为 `healthy / runtime_ready`，`events_received/events_applied=14/14`、发送 `3/3`、更新 `43/43`，event rejection、发送/更新失败与 profile mismatch 均为 0。测试群只有一位真人操作者，changed-operator rejection 继续由自动化覆盖；记录不包含真实 chat/user/message id、凭据或私人截图。
