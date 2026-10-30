# Hermes Feishu Streaming Card V4.3.7

[中文](release-notes-v4.3.7.md) | [English](release-notes-v4.3.7.en.md)

V4.3.7 恢复对 Hermes 2026-08-25 core 的安装兼容：当 `BasePlatformAdapter._process_message_background` 以 `session_key=session_key` 调用 media/local delivery filter 时，HFC 仍能精确、安全地定位 Base patch contract。

## 修复内容

- Issue #240 / PR #241：`filter_media_delivery_paths(...)` 与 `filter_local_delivery_paths(...)` 使用专用 exact matcher，同时接受旧版单位置参数调用与新版唯一 `session_key=session_key` 关键字调用。
- `install`、`setup`、`doctor` 与 installer detection 不再把新版 Hermes 报告为 `exact_delivery_contract: missing_or_unsupported`；apply/remove/restore 继续保持幂等和逐字恢复。
- 真实 Hermes source 在 `82b32f32ef6a6646a160f79c1fdf6358d271b70a` 及其父提交中均已验证该调用形态；修复针对可验证源码 contract，不依赖对单个 upstream commit 的错误归因。

## 安全边界

- 新 matcher 只接受零关键字，或唯一 `session_key=session_key`。额外关键字、错误名称/值、`**kwargs`、缺少/增加位置参数仍全部 fail-closed。
- media 与 local filter 必须分别满足自身 exact assignment contract；补丁 marker、manifest、backup、restore 和 corrupt-marker 保护不放宽。
- 本版本不改变 Feishu API payload、卡片 ownership、Gateway runtime 事件、callback authentication、delivery UUID 或归档 `legacy/` runtime。

## 验证状态

- PR #241 精确 head `5e75650b0f147a24e65d5f0e499fe8b5a3f8f22f`：patcher/detection/CLI install 定向回归 **`460 passed, 1 skipped`**；6 种对抗调用形态全部拒绝。
- 真实 upstream `gateway/platforms/base.py`：apply 成功、重复 apply 幂等、strict remove 后与原文件逐字一致。
- fresh Python 3.12 normal-wheel 环境完整 pytest：**`3330 passed, 5 skipped in 569.93s`**；`git diff --check`：**通过**。
- PR #241 的 12 项 GitHub checks 全绿；exact merge：`7fcf3cbd67d3a5100739e9e3d3d7cdcce080cb62`。release candidate CI、exact release merge、annotated tag、public tagged install 与 Release assets/checksums：**待最终门禁完成**。
- 真实飞书客户端 smoke：**未执行**。本修复只改变 installer 的 AST contract 识别；自动化不冒充平台验收。

## 致谢

感谢 @lanx214 报告新版 Hermes 安装兼容问题并提供 Linux 复现。

感谢 @PureWhiteWu 实现 PR #241 的严格 matcher、installer/detection 回归与逐字 restore 验证。
