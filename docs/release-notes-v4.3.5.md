# Hermes Feishu Streaming Card V4.3.5

[中文](release-notes-v4.3.5.md) | [English](release-notes-v4.3.5.en.md)

V4.3.5 修复 HFC `edit_message` wrapper 与 Hermes v2026.8.3 Feishu adapter 的关键字参数兼容问题，避免 completion/streaming fallback 因不受支持的内部 `metadata` 抛出 `TypeError`。

## 修复内容

- PR #235：当卡片路由未接管而回退到原 Feishu adapter 时，wrapper 检查原 `edit_message` 签名；若原方法既没有 `metadata` 形参也没有 `**kwargs`，只移除 HFC 自己消费的 `metadata` 后再调用原方法。
- 原方法显式支持 `metadata` 或 `**kwargs` 时继续完整透传，保持未来 adapter 兼容性。
- 无关未知关键字不会被兼容层吞掉，仍由原方法抛出 `TypeError`，维持 fail-closed 调试语义。

## 安全边界

- 本轮不修改 card ownership、thread placement、callback authentication、飞书 API payload、Hermes patch ownership 或归档 `legacy/` runtime。
- 签名不可检查时，只移除 wrapper-owned `metadata`；其他关键字仍保持原样，因此不会把一般编程错误伪装为发送成功。

## 验证状态

- 独立直接回归：**`4 passed`**；hook/server 热区：**`841 passed`**。
- 精确 PR HEAD 完整 pytest：**`3279 passed, 6 skipped in 599.42s`**。
- v4.3.5 docs/package/native provenance 聚焦门禁：**`99 passed`**；一次性 wheel 环境完整 pytest：**`3280 passed, 5 skipped in 555.86s`**；`git diff --check`：**通过**。
- PEP 517 sdist/wheel 与 fresh Python 3.12 wheel-only provenance：**通过**。package/distribution 均为 `4.3.5`，import 来自隔离 `site-packages`，只有一个 `hermes_agent.plugins` entrypoint，24 个 provenance slices 完整，主 CLI 与 `enable/disable --help` 均为 exit 0。
- PR #235 HEAD `5b3bf428eb688df4b95607cba1a4ce50e2eeb8d0` 的 Tests run `32719244038` attempt 3 与 CodeQL run `32719244032`：**通过**。前两次只因 GitHub HTTP 429 导致 fixed Hermes fixture 克隆失败，第三次 fixture 与全部平台 job 均通过。
- exact PR merge：`d56555bf9e716de67ed14f8ed992df1ec55cea21`。release PR、exact release merge、tag 与 Release assets/checksums 按发布流程继续执行。

## 致谢

感谢 @Lite-G 报告、复现、测试并实现 PR #235。
