# Hermes Feishu Streaming Card V4.3.2

[中文](release-notes-v4.3.2.md) | [English](release-notes-v4.3.2.en.md)

V4.3.2 修复 Issue #227 中 clarify/approval 点击后的两层飞书卡片方言问题。V4.3.1 已能让 WebSocket callback 唤醒 Hermes，但 pending 选项使用 legacy 交互卡，完成后却把同一消息当成 schema 2.0 streaming card PATCH；Gateway callback 同时会把 schema 2.0 卡作为 raw callback card 返回。真实飞书分别以 `230099/200800` 和 `200673` 拒绝这两种跨方言更新。

## 修复内容

- schema 2.0 streaming message 始终保留为当前 turn 的唯一 PATCH owner。发出 legacy clarify/approval 卡后，不再把它晋升到 `FEISHU_MESSAGE_IDS_KEY`。
- legacy 交互卡只承担用户选择。完成或过期时，`/card/actions` 返回同为 legacy 方言的无交互终态卡，移除 button、form、callback token 与其他回调凭据。
- 用户完成选择后，Hermes 后续 answer/thinking/tool/terminal 更新继续 PATCH 原 schema 2.0 streaming message；standard interaction 与 runtime-admission 两条发送路径使用同一 ownership 规则。
- Gateway 新增 callback 方言保护：如果 sidecar 意外返回 schema 2.0 card，direct-select 与 form-submit 都改为 success toast，不再构造会触发 `200673` 的 raw callback card。
- 新增模拟飞书不可跨方言 PATCH 的 `DialectAwareFeishuClient` 回归，明确拒绝把 schema 2.0 卡 PATCH 到 legacy message，覆盖标准交互、runtime admission、连续交互、过期、predecessor PATCH 失败与后续流式恢复。

## 安全边界

- callback token、interaction id、chat/operator/profile binding、过期、幂等、runtime admission 与 fail-open 边界不变。
- legacy 终态卡不包含可再次触发的 control 或 callback credential；日志与测试不记录真实 chat/message/user id、用户答案或凭据。
- `legacy/` 归档 runtime、Hermes patch ownership、Feishu token/发送 API 与普通卡片更新 API 均未改动。
- 空值 `/card` fallback 是独立 follow-up，不在本次卡片方言修复中扩大范围。

## 验证状态

- renderer、Gateway hook、sidecar server 与 Feishu SDK compatibility 联合回归：`932 passed, 1 skipped`。
- 隔离候选 Python 3.12 完整 pytest：`3253 passed, 5 skipped in 413.97s`。PEP 517 sdist/wheel 构建通过；全新 venv 固定 `lark-oapi 1.6.8` 并只从候选 wheel 安装 HFC 后，package/distribution version 均为 `4.3.2`，import origin 位于该 venv 的 `site-packages`，Hermes plugin entrypoint 精确为 1，24 个 provenance slices 齐全，主 CLI 与 `enable/disable --help` 均 exit 0。
- GitHub CI、exact merge SHA、public tag/install、Release assets 与 checksum 按 [发布准备说明](release-readiness.md) 记录；只有实际完成后才标记通过。
- 真实飞书 direct choice 与 custom-input form 验收在发布流程中单独执行。自动化通过不冒充真实客户端证据；若发布前无法获得可用测试会话，Issue #227 保持 Open 并请求报告者复测。

## 致谢

- 感谢 @saulgoodmanngabriel 提供 Hermes 0.20.0 + hfc 4.3.1 + lark-oapi 1.6.8 的完整复现、`230099/200800` 计数与“普通卡成功、交互卡失败”的决定性直连 API 对照。
- 感谢 @lyp88997 提供 toast-only `200673` 修复方向和不同环境下的更新观察，帮助把 callback 响应问题与消息更新问题拆成两层。
