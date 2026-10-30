# Hermes Feishu Streaming Card V4.3.0

[中文](release-notes-v4.3.0.md) | [English](release-notes-v4.3.0.en.md)

V4.3.0 为 Hermes Agent `v2026.8.3`（0.20.0，固定 commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`）增加经过源码能力探测的 Hybrid 集成：可验证的 Hermes Plugin hooks 负责原生生命周期，缺失的 UI/投递边界由 17 个精确 patch group 补齐。Sidecar 仍是唯一飞书卡片 owner；未知、不完整或不匹配的能力证据继续 fail-closed 到不安装，而不是猜测兼容。

## Hermes 0.20 Hybrid 集成

- 新增正式 `hermes_agent.plugins` entry point、真实 `PluginContext` 注册和进程级 signed runtime bootstrap；hook 异常保持 fail-open，不把 Hermes 对象或完整回答长期留在全局状态。
- 固定 tag probe 同时绑定源码 commit、9 个完整源码哈希、24 个 call-site slice、运行时 Python、`site-packages` origin、distribution/entrypoint 与真实 PluginManager subprocess evidence。版本号或 `VALID_HOOKS` 本身不再被当成能力证明。
- 固定 tag 使用 17 个 closed patch group，分布在 `gateway/run.py`、`agent/turn_context.py`、`agent/turn_finalizer.py`、`tools/approval.py`、`tools/delegate_tool.py`、`cron/scheduler.py` 与 `gateway/platforms/base.py`。每个 target 都有外部 expected matrix、编译检查、精确 detect/remove 和 verified-original SHA-256。
- `manifest_version: 3` 绑定 Hermes home、lexical venv Python、resolved interpreter、purelib/platlib、HFC entrypoint、官方 plugin enable 配置前像、7 个源码 backup 和 transaction phase。`install` 幂等；`repair` 可收敛 `prepared` / `plugin_enabled`；`restore` / `uninstall` 逐字恢复配置与全部源码。

## 交互、卡片与运行时

- Sidecar `/events` 增加 event-id single-flight fence、首次状态/JSON 精确重放、冲突拒绝、pending 不驱逐和 completed TTL/LRU；subagent 使用独立 timeline，不再混入 tool count。
- approval、clarify 与 slash interaction 通过独立 loopback signed callback listener 直接唤醒 Hermes 原始 pending handle/future；callback 在所有 session/message lock 外执行，成功后才转移卡片终态，失败、过期或 session replacement 保持 pending 或安全拒绝。
- 修复 Issue #217 的重复授权卡与授权不生效：Hybrid approval round-trip 只保留一个 UI owner，并绑定 exact `turn_id`、`tool_call_id` 与 pending handle。
- 修复 Issue #210/#211：冻结 predecessor 卡显示真实终态统计，连续 clarify 的已选回显绑定当前 interaction；PR #213 的完成态 hover 保留原问题和选项上下文。
- 修复 Issue #221：stable tool callback 安装在 Hermes core 最终 callback assignment 之后，工具项不再永久停在 running。
- 修复 Issue #222，并吸收 PR #223 的目标：`interaction.select` 只对可判定的 transient transport failure 做有界重试；canonical 成功、冲突和未知结果不会重复提交选择。
- PR #220 的完成通知改为显式 opt-in，通知身份、profile/chat 路由和发送结果保持受约束；PR #218/#219 的 CodeQL action 同步更新为同一受审版本。

## 安装、升级与常驻

- 修复 Issue #214：Hermes `2026.8.3` 不再落入“sidecar 正常但卡片永不启用”的 unsupported path；安装器先证明能力，再生成 Hybrid patch。
- 修复 Issue #215：已验证 Hermes 升级可通过 `install --accept-hermes-upgrade --yes` 恢复旧 ownership 后重新探测；源码、backup、manifest 或配置有漂移时仍拒绝自动修复。
- 修复 Issue #212 的 stale pidfile 恢复死锁：跨 boot 或确认 PID 已复用的旧记录会安全清理，未知活进程不会被 kill 或接管。
- 新增 `hermes-feishu-card enable --config ... --hermes-dir ... --yes` 与 `disable`。`enable` 创建真实 systemd user unit，要求 `loginctl` 已启用 linger，绑定 config/env/Hermes/runtime identity，并使用 `Restart=on-failure`；unit 与私有 manifest 以 SHA-256 互证。漂移、未知同名 unit、停服失败或不完整 ownership 都不会被静默覆盖或删除。

## 社区问题边界

- Issue #216 报告的是飞书平台没有通过长连接推送 `card.action.trigger`。如果平台端事件为零，HFC 无法从本地重建用户点击；V4.3.0 不宣称修复该平台投递问题。请按飞书验收清单核对事件订阅、发布版本、应用身份与真实事件日志。
- PR #203 仅修改归档 `legacy/`，未并入 active runtime；V4.3.0 不恢复双 runtime，也不扩大 `legacy/` 维护范围。

## 已验证范围

- 在固定 Hermes `v2026.8.3` 的独立副本中完成真实 venv entrypoint、能力 probe、17 groups / 7 targets render+compile、重复 install manifest 哈希不变、restore 后 Git 零差异、配置 SHA-256 精确恢复和 ownership evidence 清理。
- V3 installer/restore/script 联合门禁：`340 passed, 5 skipped`；persistent service 与既有 process/CLI loopback 回归：`302 passed`。
- 完整 pytest：`3227 passed, 6 skipped in 378.84s`。`python -m build --no-isolation` 生成 `hermes_feishu_streaming_card-4.3.0.tar.gz` 与 `hermes_feishu_streaming_card-4.3.0-py3-none-any.whl`；全新 Python 3.12 venv 从 wheel 安装后，package origin 位于该 venv 的 `site-packages`，Hermes plugin entrypoint 精确唯一，24 个 provenance slices 齐全，主 CLI 与 `enable/disable --help` 均为 exit 0。
- 上述结果是 local RC，不是已发布 tag 或真实飞书客户端验收。
- exact merge SHA、远端 CI、annotated tag、Release assets、checksums 与 public tag 安装仍属于后续发布流程，当前分支不会自动执行这些外部动作。

## 升级

```bash
export HFC_VERSION=v4.3.0
bash install.sh --hermes-home ~/.hermes
```

安装完成后可选择启用 Linux 开机常驻：

```bash
loginctl enable-linger "$USER"  # 需要时由管理员/用户显式执行
hermes-feishu-card enable \
  --config ~/.hermes_feishu_card/config.yaml \
  --hermes-dir ~/.hermes/hermes-agent \
  --yes
```

验证：

```bash
hermes-feishu-card doctor --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent
```
