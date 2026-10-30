# Hermes Feishu Streaming Card V4.2.7

发布日期：2026-08-05

V4.2.7 修复 Issue #193，并整合 PR #180、PR #181 的 Windows 安装与 detached runner 修复。

## 修复内容

- **Issue #193 — 冷启动探针超时**：Feishu SDK 检查和 HFC runtime import 两个隔离探针都从 8 秒调整为 30 秒，覆盖 Windows/Python 冷启动但仍保持有界失败。
- **Issue #193 — manifest 路径**：新的 ownership manifest 与 recovery plan 始终写 POSIX `/` 相对路径；旧 Windows manifest 中精确的反斜杠 Base 路径仍可重装和恢复。
- **PR #180 — parent `HERMES_HOME`**：config discovery 会检查 Windows 常见的 parent `HERMES_HOME` 布局，不再因配置位于父目录而漏报。
- **PR #181 — detached runner PID**：Windows venv detached launcher 可把 owned pidfile 从已验证的 parent launcher 安全重绑到真实 runner child。
- **PowerShell 失败传播**：`install.ps1` 显式检查 native `pip` 与 `setup` 的退出码；失败立即停止，不会继续打印 `done`。

## 安全边界

- 只有 `win32 + detached + exact process token + pidfile PID == runner parent PID` 才允许 PID 重绑，写入后还必须严格回读 `{pid, token, manager}`。
- legacy 路径兼容只接受精确预期相对路径；绝对路径、路径穿越、多余组件和额外后缀继续拒绝。
- 未知 Windows launcher、manager、token 或 parent 证据继续 fail-closed；其他平台行为不变。
- tag 只会在精确 main merge SHA 的干净 detached worktree 完成全量验证后创建。

## 安装

```bash
export HFC_VERSION=v4.2.7
bash install.sh
```

Windows PowerShell：

```powershell
$env:HFC_VERSION = "v4.2.7"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.7/install.ps1" | iex
```

安装后可运行：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card status --config /path/to/config.yaml
```

包内 Python import 应来自目标环境的 `site-packages`，package/distribution 版本均为 `4.2.7`。

## Release assets

- `hermes-feishu-card-v4.2.7-macos.tar.gz`
- `hermes-feishu-card-v4.2.7-linux.tar.gz`
- `hermes-feishu-card-v4.2.7-windows.zip`
- `hermes-feishu-card-v4.2.7-checksums.txt`

下载后请按 checksums 文件核对 SHA-256。
