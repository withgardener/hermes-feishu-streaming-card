# Hermes Feishu Streaming Card V4.2.2

发布日期：2026-08-01

V4.2.2 修复飞书/Lark WebSocket 私聊 `/update` 确认卡的状态写回缺口。V4.2.1 已能在 Gateway 重启后的第一条消息创建证据完整的确认卡，但按钮回调把 durable operation 更新为 `cancelled` 或 `locking` 后，只把新卡片放在 sidecar HTTP 响应里；Gateway 的后台转发只消费 `operation_id`，不会把这个响应渲染回飞书。因此取消后原卡片仍看起来可以点击。

## 修复内容

- native card action 继续先返回空 ACK，避免 Feishu API 延迟占用 WebSocket callback deadline。
- sidecar 在 ACK 后异步 PATCH 原 confirmation message，使 durable operation 与可见卡片保持一致。
- 取消会显示“已取消更新”终态，并且不会调度或启动 updater。
- 确认会先尝试显示 locking/准备更新状态，再调度独立维护任务。
- PATCH 仍按原 delivery 记录选择对应 bot/profile；缺失 inspection、delivery 或 message id 时安全结束，不猜测目标。

## 不变的安全边界

- 仅飞书私聊中的精确裸 `/update` 进入专用维护流；群聊、非飞书、别名和带参数命令仍由 Hermes 原处理器负责。
- 发起者、chat、profile、target evidence 与 120 秒有效期绑定不变。
- tracked worktree、Git 中间态、hook/integrity、active-work 聚合、drain marker、cached wheel、版本和最终 runtime 验证仍 fail-closed。
- 取消动作本身不执行 `hermes update`，也不修改 Hermes checkout。

## 自动化与真实验收

- 新增真实 callback 边界回归：创建 private update confirmation，POST cancel action，等待后台 publisher PATCH 原 message，并断言终态文案出现。
- operations/server/hook-runtime 相关矩阵：`378 passed`。
- Python 3.9 / 3.12 全量均为 `2307 passed, 5 skipped`；`git diff --check`、wheel/sdist、干净 Python 3.12 `site-packages` 包/distribution/CLI provenance 与独立 maintenance runtime 4.2.2 已通过。PR CI 与精确 merge SHA 会在发布链路继续复验。
- 发布后在真实飞书私聊把 `/update` 作为 Gateway 重启后的第一条消息，点击取消并确认原卡进入“已取消更新”终态；同时确认 Hermes 版本未变化、updater 未运行。

## 安装

```bash
export HFC_VERSION=v4.2.2
bash install.sh
```

升级现有安装后请重新运行官方 `setup` / `install`，让 Hermes runtime venv、managed hook、sidecar 和独立 maintenance runtime 使用同一个 V4.2.2 包；不要手工修改 `gateway/run.py`。

## Release assets

- `hermes-feishu-card-v4.2.2-macos.tar.gz`
- `hermes-feishu-card-v4.2.2-linux.tar.gz`
- `hermes-feishu-card-v4.2.2-windows.zip`
- `hermes-feishu-card-v4.2.2-checksums.txt`

下载后请按 `hermes-feishu-card-v4.2.2-checksums.txt` 核对 SHA-256。
