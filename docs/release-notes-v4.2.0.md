# Hermes Feishu Streaming Card v4.2.0

## 新功能

- 在飞书私聊发送裸 `/update`，会先检查 Hermes、Git 工作树、HFC 钩子、更新目标、运行任务和维护包，再显示 120 秒有效的确认卡。
- 确认后由 Hermes 安装目录之外的独立维护进程执行官方 `hermes update --yes`，并从私有缓存重新安装**当前同一 HFC 版本**，恢复 hook、sidecar 和 Gateway。
- 同一卡片持续显示等待任务、恢复 hook、更新 Hermes、重装 HFC、启动服务、验证以及最终结果。
- 新增本机恢复入口：
  - `hermes-feishu-card maintenance provision`
  - `hermes-feishu-card maintenance status`
  - `hermes-feishu-card maintenance run`
  - `hermes-feishu-card maintenance resume`

## 安全边界

- 仅拦截飞书私聊中的裸 `/update`。群聊、非飞书、别名和带参数调用仍进入 Hermes 原处理器。
- 确认绑定发起人、私聊、profile、预检快照与本机证据，并在 120 秒后失效；它明确授权官方 updater 在执行时重新 fetch 最新 `origin/main`，重复或跨用户点击会被拒绝。
- 确认后先写入持久化维护准入锁，Gateway 暂停接入新任务；只有连续两次新 heartbeat 都证明 sidecar 与 Gateway 活跃任务为零，才停止服务并开始更新。缺少新协议任务计数时拒绝进入维护。
- 预检显式 fetch 并展示当前 `origin/main` 快照，不采用 fork 的 `upstream/main` 摘要。官方 updater 会按自身语义再次 fetch 最新 `origin/main`；若远端在确认后推进，流程仍先恢复新版本 HFC、hook 与服务，再以失败终态透明报告 target mismatch，不把快照漂移声明为原目标成功，也不把机器留在停服状态。
- 只执行官方 updater，不使用 `--force`、`--force-venv`、`--no-backup`，不执行自定义 `reset`、`checkout`、`stash` 或 Git 回滚。
- 保留 untracked 文件；存在非 HFC 的 tracked 改动、未完成 Git 操作、维护包漂移或运行时验证失败时停止。
- 独立维护 venv 安装 wheel 的完整依赖并实际导入 maintenance runner；一次性私有凭据快照由 runner 启动时消费，终态/孤儿快照会被清理；Linux 必须使用可验证的 `systemd --user` 独立 manager，无可用 manager 时拒绝启动，不猜测 detached 子进程是否能脱离 cgroup。
- Gateway heartbeat 必须证明聚合计数来自单次 `_active_work_count()` 采样，并确认运行中的 `HERMES_HOME` 与 checkout 的 drain marker 目录一致；secondary/custom home 不满足该证据时拒绝卡片自动更新。
- 完成态同时核对新的 sidecar PID、新的 Gateway runtime identity、fresh heartbeat、HFC 版本、Hermes venv Python identity、`site-packages` 导入来源和 managed hook。
- 维护目录为私有权限，journal 不记录 Feishu secret、transport secret、原始命令输出或任意命令。

## 验收建议

1. `maintenance status` 显示 `ready`。
2. 在飞书私聊发送 `/update`，检查确认卡中的 Hermes/HFC 版本与目标。
3. 验证取消不会执行更新。
4. 再次确认更新，观察原卡片完成全部阶段。
5. 完成后运行 `doctor --explain`，确认 HFC 版本、`site-packages` 导入来源、hook 与 sidecar/Gateway 状态。

## Release 附件

- `hermes-feishu-card-v4.2.0-macos.tar.gz`
- `hermes-feishu-card-v4.2.0-linux.tar.gz`
- `hermes-feishu-card-v4.2.0-windows.zip`
- `hermes-feishu-card-v4.2.0-checksums.txt`
