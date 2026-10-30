# V4.0.20 发布说明

发布日期：2026-07-22

V4.0.20 修复 Issue #153：已有卡片的 `system.notice` 已经由 sidecar 接管并排队异步 PATCH 时，hook 不再因为缺少同步 `delivered` 结果而误发“投递结果无法确认”的灰色提示。

## 修复

- `/events` 只在 notice 已应用且异步 PATCH 任务已排队后返回 `delivery.outcome=accepted`；该结果必须同时带有 `applied=true`。
- hook 明确认可 `accepted + applied=true`，缺少明确 applied ACK 时继续 fail-open。
- 独立 notice 的初始 create/reply 仍返回 `delivered`、`not_sent` 或 `unknown`；本修复不等待每次 PATCH，也不把“已排队”伪装成“已送达”。

## 可观测性

- `/health.metrics.notice_update_failures` 统计 accepted notice 的异步更新任务在内部 PATCH 重试耗尽后仍失败的次数。
- `last_update_error` 仅附加白名单校验后的 `status_code` / `api_code`；响应正文、token、URL、凭据与原始标识符不会进入诊断。

## 验证

- hook/server 聚焦回归：explicit accepted ACK、缺失 applied、已有卡片排队更新、故障重试与脱敏诊断均通过。
- 全量自动化：`1517 passed, 4 skipped`。
- sdist/wheel 构建与隔离 Python 环境 `site-packages` 导入版本 `4.0.20` 通过。
- 发布资产：
  - `hermes-feishu-card-v4.0.20-macos.tar.gz`
  - `hermes-feishu-card-v4.0.20-linux.tar.gz`
  - `hermes-feishu-card-v4.0.20-windows.zip`
  - `hermes-feishu-card-v4.0.20-checksums.txt`

## 升级

```bash
export HFC_VERSION=v4.0.20
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```
