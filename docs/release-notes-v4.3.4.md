# Hermes Feishu Streaming Card V4.3.4

[中文](release-notes-v4.3.4.md) | [English](release-notes-v4.3.4.en.md)

V4.3.4 修复 runtime interaction listener 的启动/退出可靠性，并让 `doctor --json` 使用正确的 V3 安装契约诊断 Hermes 0.20 Hybrid 安装。

## 修复内容

- PR #229：listener bind 直接完成 socket 绑定，不再触发 `socket.getfqdn()` reverse-DNS 查询；`serve_forever` thread 设为 daemon，因此短命令即使未显式调用 `close()` 也能正常退出。
- Issue #233：检测到 `manifest_version: 3` 后，doctor 使用 V3 runtime binding、plugin entrypoint 与 fixed-tag Hybrid inspector，不再调用 Legacy install diagnosis、recovery 或 integrity-repair planner。有效安装报告 `installed`，不会再出现 Legacy manifest/hash/path/source 误报。
- hosted macOS 的 blocked-delivery close 回归改用 Future deadline 验证有界完成，排除 runner 调度开销导致的临界抖动；生产 `_CLOSE_JOIN_SECONDS` 保持不变。

## 安全边界

- V3 phase、plugin config、patched target、backup 或 runtime identity 漂移继续 fail-closed，并输出 V3-specific finding。V3 manifest 不提供 Legacy 自动 repair，只引导使用官方 V3 restore/reinstall 流程。
- listener 的 loopback/显式 host 策略、runtime interaction token/authentication、callback ownership、飞书 card/API 投递语义、Hermes patch ownership 与归档 `legacy/` runtime 均未改变。
- PR #228 未包含在本版本：其 disable 配置合并优先级、跨卡片方言更新边界与当前 main 冲突仍需贡献者处理。

## 验证状态

- #229 listener/daemon、#233 V3 install/doctor 正常与篡改矩阵、diagnostics/CLI 以及 hosted-macOS timing 联合回归：**`191 passed`**。
- 一次性 4.3.4 venv 的完整 pytest：**`3275 passed, 6 skipped in 634.95s`**；`git diff --check`：**通过**。
- PEP 517 sdist/wheel 构建与 fresh Python 3.12 wheel-only provenance：**通过**。package/distribution 均为 `4.3.4`，import 来自隔离 `site-packages`，只有一个 `hermes_agent.plugins` entrypoint，24 个 provenance slices 完整，主 CLI 与 `enable/disable --help` 均为 exit 0。
- PR #234 candidate HEAD `435ea4e355719e0f2d904cf1bac986ff18f70876` 的 Tests run `32710110323`（10 jobs）与 CodeQL run `32710110375`：**通过**，覆盖 Ubuntu Python 3.9–3.12、macOS、Windows、PowerShell installer、Docker Compose、Feishu SDK 与 fixed Hermes fixture。
- exact merge/tag 与 Release assets/checksums 按发布门禁继续执行，完成前不标记通过。
- 本轮不修改飞书卡片或 API delivery semantics，因此不发送额外真实飞书测试消息；这不替代 V4.3.3 尚未完成的 first-reply thread 客户端验收。
