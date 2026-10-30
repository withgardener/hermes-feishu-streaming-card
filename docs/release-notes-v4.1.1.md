# V4.1.1 发布说明

[English](release-notes-v4.1.1.en.md) | [中文](release-notes-v4.1.1.md)

V4.1.1 是 V4.1.0 的升级恢复安全热修。它不改变 per-chat 原生策略、表格 compact 或 native handoff 的产品行为，重点收紧首次 heartbeat、人工 review fence、旧 sidecar 进程迁移与 setup 解释器一致性。

## 修复内容

- 已验证的 Hermes on-disk plan 为 `installed`、但 sidecar 尚未收到首次 `runtime.hello` / `runtime.heartbeat` 时，仅保持 `runtime_heartbeat_waiting` / `runtime_heartbeat_missing`；等待状态不会写入持久化 restart/manual-review fence。
- 新增 `integrity acknowledge-review`。它会两次验证 Hermes plan、sidecar health 与 pidfile，并要求 target-bound fence、跨进程锁和未变化的 CAS snapshot；任何一项不满足都 fail-closed。
- V4.1.0 产生的未绑定 fence 只在 `restart=true + manual=true + pre_repair_runtime_hash` 为空这一精确形态下允许显式迁移。未绑定的非空 hash fence 保持拒绝；已绑定的非空 hash fence只清除 manual-review 位并保留 Gateway restart fence，直到收到不同 runtime id 且 generation/package 匹配的新 `runtime.hello`。
- 旧版 `0644` pidfile 只在当前用户拥有、非 symlink、权限为 `0700` 的私有 state dir 中作为迁移候选，并通过已打开 fd 的 identity 绑定收紧为 `0600`。目录、inode、内容形状、进程或 health identity 在校验期间变化都会拒绝迁移。
- pidfile-less 的运行中 sidecar 不会被自动接管或 kill。detached 子进程必须先看到父进程写入的精确 PID + process token 管理记录，才会读取配置并监听端口；父进程写入失败时子进程自行退出。受管 sidecar 只通过 loopback + process token 认证请求让进程自停，不再向数字 PID/PGID 发送 TERM/KILL；旧进程不支持自停接口或超时时，保留进程与 pidfile 并要求人工处理。
- `setup/install` 使用 `python -I` 隔离复检 Hermes runtime venv，要求 package 来自该 venv 的 `site-packages`，再根据 `/health` 的 package version 与 Python identity 判断是否受管重启。普通 `start` 同样要求隔离 import 与版本匹配，并把已验证的 canonical Hermes root 显式传给 runner，不能被冲突的环境变量重新定向；`start/status/stop` 共享显式 `--env-file`。
- 显式启用具体 non-loopback 地址时，业务监听继续强制事件鉴权，同时增加同地址族的独立 loopback 管理监听，供本机 health 与 process-token shutdown 使用；wildcard 监听不再额外重复绑定。

## 安全恢复顺序

```bash
# 1. 先确认 Hermes 安装和安全状态；不要手改 gateway/run.py
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain

# 2. 人工停止旧 sidecar，确认 health 不可达且 state dir 内无 pidfile
hermes-feishu-card stop --config CONFIG

# 3. 仅在 doctor 确认 installed 且 manual review 无法由 runtime 自清时执行
hermes-feishu-card integrity acknowledge-review \
  --config CONFIG \
  --hermes-dir HERMES_DIR \
  --state-dir STATE_DIR \
  --yes

# 4. 重跑官方 setup，然后人工重启 sidecar 与 Hermes Gateway
hermes-feishu-card setup --config CONFIG --hermes-dir HERMES_DIR --yes
```

`acknowledge-review` 不是强制清障开关：dirty target、未知 backup/manifest、非私有 fence、仍在运行的 sidecar 或残留 pidfile 都必须先人工处理。命令完成后仍需人工重启 sidecar 与 Hermes Gateway，并由新 `runtime.hello` 证明 readiness。

## 安装

```bash
export HFC_VERSION=v4.1.1
bash <(curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh)
```

Docker Compose 示例默认使用 `v4.1.1`。升级前请备份本机配置与 `.env`；不要提交 Feishu secret、真实 chat id、pid token、runtime id 或 recovery fingerprint。

## 发布验收状态

候选提交 `20b7b06` 已完成以下门禁：

- 完整 pytest：`2194 passed, 4 skipped`；`git diff --check` 通过；
- wheel/sdist 构建、隔离 `site-packages` import/version provenance 通过；
- wheel 安装后的真实进程测试：`8 passed`；独立代码审查无 P0–P2。

以下 post-candidate / post-tag 项目仍需在发布流程中完成，本文不提前声称通过：

- Python 3.9 / 3.12 CI、exact merge SHA 回归；
- 公开 tag 安装与 Release assets；
- Linux 四种 manager、Docker 普通非 privileged topology；
- 本机与远端 upgrade/restart、真实 Hermes model 与真实飞书 card/native/card smoke；
- heartbeat 等待不写 fence、empty/non-empty hash acknowledge 分支、legacy `0644` 与 pidfile-less 拒绝路径。
