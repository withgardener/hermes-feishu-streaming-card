# V4.1.2 发布说明

[English](release-notes-v4.1.2.en.md) | [中文](release-notes-v4.1.2.md)

V4.1.2 是 V4.1.1 的窄范围运行时热修。它修复正常重启 Hermes Gateway 时，短暂的 heartbeat stale 窗口被误写成持久化 restart fence、从而要求用户再次重启的问题；同时修复真实 Hermes 工具调用被稳定 lifecycle callback 与旧 progress callback 各记录一次的问题。

## 修复内容

- 当 Hermes on-disk integrity plan 已验证为 `installed` 时，`runtime_heartbeat_waiting`、`runtime_heartbeat_missing` 和 `runtime_heartbeat_stale` 都只表示当前 runtime readiness 尚未就绪；这些 liveness 状态不会自行创建持久化 restart/manual-review fence。
- Gateway 重启期间 readiness 仍保持 degraded；不同 runtime id、generation/package 匹配的新 `runtime.hello` 到达后会直接恢复 `runtime_ready`，不再需要第二次重启。
- 当 Hermes 已安装带稳定 `call_id` 的 tool start/complete callbacks 时，旧 progress callback 通过检查 agent 上实际安装的 wrapper 退出，不再把同一次工具调用以工具名再记录一遍。若稳定 callback 未被卡片路径接受，显式 fallback 标记仍允许 Hermes 原生进度 fail-open。
- generation/package 不匹配、控制面鉴权不可用、既有 manual-review/restart fence 和真正执行过的 strict repair 继续 fail-closed。HFC 仍不会自动重启 Hermes Gateway。

## 升级

继续使用官方安装路径，不要手工修改 Hermes 源码：

```bash
export HFC_VERSION=v4.1.2
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain
hermes-feishu-card setup --config CONFIG --hermes-dir HERMES_DIR --yes
```

若 `doctor` 明确要求重启 Gateway，请先确认无活动会话，再使用 Hermes 自己的服务命令重启一次；随后重新检查 `status` / `doctor`，应看到 `readiness: ready` 与 `runtime_ready`。

## 验收范围

- 自动化覆盖已安装 plan、旧 runtime hello、heartbeat stale、coordinator check、新 runtime hello 以及 fence 文件不存在的完整竞态顺序。
- patcher 回归覆盖 stable wrapper 检测与显式 fallback；真实飞书验收要求一次 terminal 调用只出现一个带耗时的时间线条目。
- 发布门禁还包括完整 pytest、构建与隔离 `site-packages` provenance、精确 merge SHA、公开 tag/install、Release assets、本机与远端 macOS 升级、真实 Hermes 配置模型与飞书流式卡片。
- 本版本不测试或改变自动压缩行为。
