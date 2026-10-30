# Hermes Feishu Streaming Card V4.2.6

发布日期：2026-08-04

V4.2.6 修复 Issue #187、#188、#189 与 PR #190，并修复本机飞书裸 `/update` 在标准 venv symlink 环境中的更新失败和 Hermes 0.20 版本误报。

## 修复内容

- **Issue #187 — 重复选项卡位置**：活动会话每次收到 `interaction.requested` 都发送一张完整的新选项卡，并把新 message id 提升为后续更新目标。旧卡保留历史快照；新卡发送失败会恢复请求前状态，允许 Hermes 安全重试。
- **Issue #188 — 终态短后记覆盖正文**：当已流式输出的是完整长答案，而 terminal completion 只追加很短的校验/收尾说明时，两段内容会在正文区以分隔线保留。正常完整终态仍会替换短进度前言。
- **Issue #189 / PR #190 — Hermes Agent 0.20**：仅在已验证的 exact Base ledger anchors 内接受 `await asyncio.to_thread(...)` 同步写入包装。缺少 `await`、未知 wrapper、顺序改变或 anchor 不精确仍然 fail-closed；安装和移除保持逐字节可逆。
- **飞书裸 `/update`**：runtime 绑定和独立维护进程保留标准 venv `bin/python` 的 lexical symlink 路径，避免丢失 venv `site-packages`；只读更新检查与 target fetch 的 fail-closed timeout 调整为最多五分钟，避免慢 Git fetch 被误判失败。
- **Hermes 0.20 版本显示**：缺少根目录 `VERSION` 时，检测器先静态读取 `hermes_cli.__version__` 的 literal assignment，再回退 Git tag；doctor 和更新卡不再把 `0.20.0` 显示成旧 calendar tag。

## 安全边界

- 不导入 Hermes 来探测版本，也不接受动态、拼接或不可静态证明的版本表达式。
- 未知 Hermes source shape 继续拒绝 patch；unknown/unsupported event path 继续 fail-open。
- `/update` 的发起人、会话、profile、target evidence、drain、快照和恢复验证边界不变。
- tag 只会在精确 main merge SHA 的干净 detached worktree 完成全量验证后创建。

## 安装

```bash
export HFC_VERSION=v4.2.6
bash install.sh
```

安装后可运行：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card maintenance status
```

## Release assets

- `hermes-feishu-card-v4.2.6-macos.tar.gz`
- `hermes-feishu-card-v4.2.6-linux.tar.gz`
- `hermes-feishu-card-v4.2.6-windows.zip`
- `hermes-feishu-card-v4.2.6-checksums.txt`

下载后请按 checksums 文件核对 SHA-256。
