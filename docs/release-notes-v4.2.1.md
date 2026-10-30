# Hermes Feishu Streaming Card v4.2.1

## 修复

- Gateway 启动安装 Feishu command-card adapter 时，会先登记 live Gateway runner，再启动认证 runtime control。
- 首个 `runtime.hello` / `runtime.heartbeat` 现在就能从同一次 `_active_work_count()` 采样证明 turn、cron 与 API 的完整聚合计数。
- 修复 Gateway 重启后的第一条飞书私聊裸 `/update` 可能因 heartbeat 尚未绑定 runner 而被拒绝、需要其他消息预热后重试的问题。

## 安全边界

- 不放宽维护准入：缺失、异常、负数、布尔值或非整数的聚合结果仍视为证据不完整，不能按零任务继续。
- 外部 drain、连续 heartbeat、`HERMES_HOME` 匹配、同版本 HFC 恢复与所有 v4.2.0 门禁保持不变。

## 验收建议

1. 安装后重启 Hermes Gateway，不先发送其他消息。
2. `/health` 中确认 `readiness.status=ready`、`active_work_count_complete=true`、`drain_home_verified=true`。
3. 第一条飞书私聊消息直接发送裸 `/update`，应进入 120 秒确认卡，而不是提示维护证据不足。

## Release 附件

- `hermes-feishu-card-v4.2.1-macos.tar.gz`
- `hermes-feishu-card-v4.2.1-linux.tar.gz`
- `hermes-feishu-card-v4.2.1-windows.zip`
- `hermes-feishu-card-v4.2.1-checksums.txt`
