# Hermes facade 拆分适配（fork）

本页记录针对 Hermes `79445a496c` 源码布局的 Legacy patcher 适配。
源码拆分本身不构成 native hook 能力证明；`MIN_SUPPORTED_VERSION`、固定 tag
的 Hybrid/V3 安装入口与既有 native-hooks/hybrid/legacy-patch 选择规则保持不变。

## 锚点与目标文件

| 文件 | Hook |
| --- | --- |
| `gateway/run_turn.py` | message.started、completion、调用方耗时传递；校验 post-turn `agent:end` 调用 |
| `gateway/run_turn_runner.py` | stable tool lifecycle、answer/thinking delta、status、clarify、approval |
| `gateway/run_inbound.py` | command adapter 与 `_quick_key` 前的 HFC command |
| `gateway/run_busy.py` | slash confirm |
| `gateway/run_startup.py` | startup adapter 与 ledger redelivery |
| `gateway/run_notifications.py` | platform notice |
| `cron/scheduler_delivery.py` | 媒体提取和过滤之后的 cron completion |
| `gateway/platforms/base.py` | exact final delivery 与无独立正文的 terminal |

`gateway/run.py` 和 `cron/scheduler.py` facade 也参与 ownership 证据。
检测只把实际可注入的定义视为 hook 锚点；cron 定义仍在 `scheduler.py` 时路由到
该文件，重复定义拒绝安装。doctor 的 `anchor_locations` 显示实际命中文件。
`status_callback` 仍是 optional，缺失时支持安装并显示 partial。

TurnRunner 的 `stream_delta_cb` / `interim_assistant_cb` 使用 `ctx` 传递本轮 source、
message ID、Gateway loop 和 session；approval 保留空选择时的原生回退。
completion 从调用方复制 `_turn_seconds`，不修改原始 `agent_result` 对象。

检测把 `reply_context`、`attachment_delivery` 当作 capability evidence：多个文件含有合法调用时，`capability_locations` 会完整列出排序后的文件，但不会产生 ambiguity。`anchor_candidates` 只记录真正待注入的 AST 定义候选；重复 handler、callback、completion、cron 或 exact Base seam 仍 fail-closed，并在 doctor 中显示文件/行/列。注释、docstring、字符串示例不构成 anchor evidence。


必须同时验证 `_process_message_background`、`_extract_response_content`、
`_send_final_text`、`_record_delivery_obligation` 与 `_finalize_delivery_obligation`
的调用参数、提取/过滤顺序和 ledger 契约。不能仅按函数名接受新的上游实现。

提取后的 images/local_files/media_files 通过 task-local completion stage 传给
final-send helper；ledger 仍由 Hermes 在 terminal hook 前记录并标记 attempting。
sidecar 明确接受后才用成功代理抑制原生正文，原生 ledger finalize 和附件路径继续执行。
带附件和纯媒体 terminal 不授予 text-only native ACK。缺少提取证据时清理 stage，
回退原生发送；不猜测附件为空。

## Ownership 与恢复

拆分布局使用 `manifest_version=4`、`layout=gateway-decomposed-v1`，每个受管源码文件
独立记录原始/注入 SHA-256 与同目录 backup。安装前先完成整个集合的内存渲染、编译和
逐字可逆检查，再复用 recovery 的目录绑定、原子替换与失败回滚事务。
源码集合、backup、manifest、版本文件和 Git HEAD/packed refs 证据参与 fingerprint。

重复安装不改源码。restore/uninstall 验证全部 ownership 后逐字还原源码并清理
backup/manifest；恢复锁文件遵循原有 recovery 行为保留。任意受管文件的用户编辑、
损坏 marker、缺失 backup、路径越界或 symlink 均拒绝覆盖。
已知原始文件替换了 owned hook 时可 repair，`--no-repair` 阻止自动修复。
兼容的无 marker 源码更新需要显式 `--accept-hermes-upgrade`。

V4 不伪造 V1/V2 或固定 tag V3 ownership，也不自动迁移这些旧 manifest。
`integrity.mode=safe` 的 Git provenance 自动修复仍要求原有严格证据；当前 V4 没有
这份 provenance，必须拒绝自动升级修复，不能把普通多文件 fingerprint 当成授权。
跨布局或未来 HFC renderer 变化时，先用原 installer 验证/还原旧 ownership，再安装新版本。

## 验证与后续维护

`tests/fixtures/hermes_decomposed/` 包含 8 个注入目标和两个 facade，无凭据、无运行环境。
`tests/unit/test_decomposed_patcher.py` 验证 CLI install/uninstall、重复安装、LF/CRLF
及无末尾换行的逐字往返、事务回滚、拒绝漂移、版本复核与生成 hook 的实际执行。
这些测试不代替真实 Feishu/Lark smoke；模拟 CLI 测试仅替换 runtime package/SDK provisioning。

```bash
python -m pytest tests/unit/test_patcher.py tests/unit/test_decomposed_patcher.py tests/unit/test_installer_detection.py tests/integration/test_cli_install.py -q
python -m pytest -q
git diff --check
```

本适配尚属 fork 未发布改动。未来上游 HFC release 覆盖此布局时，应比较锚点、
renderer 和 manifest 迁移行为后移除重复实现；`ac45e40` 的 20-year timeout 改动
独立保留，不随此兼容补丁或上游版本切换而隐式重置。
