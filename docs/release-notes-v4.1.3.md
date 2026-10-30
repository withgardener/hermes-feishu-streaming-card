# V4.1.3 发布说明

[English](release-notes-v4.1.3.en.md) | [中文](release-notes-v4.1.3.md)

V4.1.3 汇总三项升级兼容性修复：Issue #158 的 integrity fence binding 收敛、贡献者 @dake6767 在 PR #168 提交的同名 answer-delta 回调选择，以及 Issue #169 报告的 Hermes `TurnRunner` 重构后 tool/streaming/interaction hook 丢失。目标是在继续 fail-closed 的同时，让官方升级、诊断和卸载路径保持可验证、可逆。

## 修复内容

- `integrity acknowledge-review` 现在可原子迁移同一 Hermes target 的 plan binding，但必须同时满足：当前 recovery/integrity plan 连续两次验证为 installed、sidecar health 连续两次不可达、无 pidfile、显式 `--yes`、旧新 `target_identity` 完全一致、fence snapshot CAS 未变化。
- 不同 target identity、状态漂移、运行中的 sidecar、未知 legacy fence、dirty 或不可验证 plan 继续 fail-closed。该能力不是 force-clear。
- 若已有独立 restart fence 与非空 `pre_repair_runtime_hash`，acknowledgement 只解除 manual review 并更新 plan binding；restart/hash 保留到不同 runtime id 且 generation/package 匹配的新 `runtime.hello` 到达。
- `doctor --explain` 在 `integrity_migration_required` 时给出完整 `integrity migrate-safe` 命令；其他 manual-review 场景会先要求审查 installed evidence，再给出包含 config、Hermes 与 state 路径的完整 `integrity acknowledge-review` 命令。
- 当 Hermes 同时定义原生文本流与 streaming-TTS fallback 的同名 `_stream_delta_cb` 时，answer-delta hook 只选择调用 `_stream_consumer.on_delta` 的原生文本流；升级时会迁移旧的错误注入位置。
- 兼容 Hermes commit `1a3a9de` 引入的 `TurnRunner` seam：stable tool、answer、thinking、clarify、approval 与 status hook 通过已验证的 `TurnContext` 字段注入；status hook 只在 `ctx = self._ctx` 绑定后执行。
- doctor 的 callback capability 改由 patcher 实际可注入结果决定。存在同名 TurnRunner callback 但结构不满足安全契约时，安装明确报 `not safely patchable`，不再误报 partial/supported；旧版 Hermes 与损坏 marker 的 recovery 路径保持不变。

## 升级与恢复

继续使用官方安装与诊断入口。不要手工编辑 `runtime-integrity-fence.json`，也不要调用内部 Python 函数：

```bash
export HFC_VERSION=v4.1.3
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain
hermes-feishu-card setup --config CONFIG --hermes-dir HERMES_DIR --yes
```

若真实 Hermes 更新覆盖 hook，请先按 doctor 提示重新运行官方 `install`。当 install state 已验证为 installed 但仍为 `manual_review_required` 时，停止 sidecar，执行 doctor 给出的 `integrity acknowledge-review --config CONFIG --hermes-dir HERMES_DIR --state-dir STATE_DIR --yes`，再人工启动 sidecar 并重启一次 Hermes Gateway。最后确认 `readiness: ready`、`readiness.reason: runtime_ready` 与 `hook.status: installed`。

## 候选验收范围

- 自动化覆盖同 target plan 过渡成功、默认不放行、不同 target 拒绝、CAS/state/process/current-plan 双重校验以及 restart/hash 保留。
- 诊断覆盖 migration 与 manual review 两类完整命令，不输出真实路径、fingerprint 或状态私密证据。
- 对 Hermes `1a3a9de630a809cf1b177ec0ddf5b7ff66291e65` 的源码回归必须得到 14 个受管 hook block，6 个迁移到 TurnRunner 的 hook 各出现一次，二次 patch 幂等，`remove_patch` 逐字还原，doctor 为 `supported/full`。
- 发布前仍需 Issue #158 报告者在 Ubuntu 24.04 / 真实 Hermes upstream update 后按官方流程复测；Issue #169 报告者需在最新 Hermes 上用同一候选确认 doctor 为 full、工具调用与流式正文恢复且无原生灰字重复。不得手工修改 Hermes `gateway/run.py` 或 fence。
- exact merge SHA、公开 tag/install 与 Release assets 只在正式发布阶段完成。
