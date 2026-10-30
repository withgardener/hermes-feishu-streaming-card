# V4.0.7

V4.0.7 修复 Linux/systemd 下 sidecar 与 Hermes Gateway 生命周期耦合的问题，并合入 PR #124 的自我改进通知卡片修复。Gateway 重启不再连带杀死 sidecar；升级脚本也会优先使用 Hermes 实际 venv，避免系统 Python 与 runtime Python 安装状态分叉。

## Linux/systemd sidecar 生命周期

- Issue #125：systemd user manager 可用时，`setup` / `start` 使用独立 transient user service 启动 sidecar。
- unit 使用 `Type=exec`、`Restart=on-failure` 与短暂 restart delay；它由 user service manager 托管，不属于 `hermes-gateway` cgroup。
- 已由旧 detached-process 路径启动的 sidecar，只有在 PID、process token 与 `/health` 完全一致时才会迁移；未知进程保持 fail-closed。
- systemd 自动重启后即使 PID 改变，`status` / `stop` 仍通过 process token 和记录的 unit identity 安全管理。
- macOS、Windows、容器及无可用 systemd user manager 的 Linux 环境继续使用原 detached-process fallback。

## Python 安装路径

- `install.sh` 依次检查 Hermes 的 `venv` / `.venv` Python，再回退到 `PYTHON` 或 `python3`。
- `HFC_PYTHON` 是显式解释器覆盖入口。
- Debian/Ubuntu 的 externally managed fallback 仍保留，但正常 Hermes venv 不再误装到系统 Python。

## 自我改进通知卡片

- PR #124：原会话已结束后到达的 session-scoped self-improvement notice 不再创建新的主卡片。
- server 返回 `applied: false` 后，现有 runtime 会将通知重试为独立卡片并完成自己的 lifecycle。
- 下一轮对话继续创建和更新自己的卡片，不再覆盖陈旧的自我改进卡片。

## 贡献

- 感谢 @nasvip 提交 #125 的 systemd cgroup、PID、Python 环境与修复后 health 证据。
- 感谢 @hzy 贡献 PR #124 的 self-improvement notice 生命周期修复与回归测试。

## 验证

- systemd 生命周期、旧进程安全迁移、PID 变化后的 stop，以及 Hermes venv Python 选择均有自动化回归测试。
- PR #124 完整套件：`1317 passed, 3 skipped`；`git diff --check` 通过。
- V4.0.7 完整发布 gate：`1324 passed, 3 skipped`；`git diff --check` 通过。
- sdist 与 wheel 构建成功；干净 Python 3.12 venv 从 wheel 导入 `4.0.7` 成功。
- 公共 tag/Release assets 与 one-line install 验证将在 Release 发布后回写。

## Release assets

- `hermes-feishu-card-v4.0.7-macos.tar.gz`
- `hermes-feishu-card-v4.0.7-linux.tar.gz`
- `hermes-feishu-card-v4.0.7-windows.zip`
- `hermes-feishu-card-v4.0.7-checksums.txt`
