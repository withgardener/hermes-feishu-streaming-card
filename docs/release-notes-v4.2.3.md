# Hermes Feishu Streaming Card V4.2.3

发布日期：2026-08-01

V4.2.3 修复 V4.2.2 真实飞书验收发现的 WebSocket 回调证据转发缺口。用户点击 `/update` 确认卡后，native action 已到达 Gateway，但 hook 构造 sidecar payload 时遗漏 `update_evidence_fingerprint`。sidecar 因而按既有安全策略 fail-closed，原确认卡不会进入取消或准备更新状态。

## 修复内容

- WebSocket hook 现在从 card value 读取 `update_evidence_fingerprint`，并原样转发给 sidecar。
- 新增 executor-facing 单元回归，直接断言 hook 到 sidecar 的 payload 保留该字段；测试在修复前以缺失字段失败，修复后通过。
- native action 仍先快速返回空 ACK；卡片 PATCH 和后续维护调度仍在异步路径中执行。

## 不变的安全边界

- sidecar 继续校验发起者、chat、profile、operation token、目标证据、证据指纹与有效期；缺失或不匹配证据仍 fail-closed。
- 取消必须进入 terminal state 且绝不启动 updater；确认必须先尝试发布 locking/准备态，再调度独立维护任务。
- 仅飞书私聊中的精确裸 `/update` 使用维护卡；群聊、非飞书、别名和带参数命令保持 Hermes 原行为。
- 安装和恢复继续只通过官方 patcher/setup/install 路径；不要手工修改 `gateway/run.py`。

## 验证

- hook/runtime/server/Feishu SDK 相关矩阵已通过：`670 passed, 1 skipped`。
- 完整 pytest 已通过：`2309 passed, 5 skipped`；`git diff --check`、sdist/wheel 与干净 Python 3.12 `site-packages` 包/distribution/CLI provenance 也已通过。PR CI 与精确 merge SHA 会在发布门禁中继续复验。
- 候选包已在真实飞书私聊创建新的 `/update` 卡并点击取消：sidecar update 成功，原卡进入“已取消更新 / 未执行 Hermes 更新”终态，Hermes Git HEAD 与 `update.log` 未变化，且无 updater 进程。正式 tag 安装后再重复同一验收。

## 安装

```bash
export HFC_VERSION=v4.2.3
bash install.sh
```

升级现有安装后请重新运行官方 `setup` / `install`，让 Hermes runtime venv、managed hook、sidecar 和独立 maintenance runtime 使用同一个 V4.2.3 包。

## Release assets

- `hermes-feishu-card-v4.2.3-macos.tar.gz`
- `hermes-feishu-card-v4.2.3-linux.tar.gz`
- `hermes-feishu-card-v4.2.3-windows.zip`
- `hermes-feishu-card-v4.2.3-checksums.txt`

下载后请按 `hermes-feishu-card-v4.2.3-checksums.txt` 核对 SHA-256。
