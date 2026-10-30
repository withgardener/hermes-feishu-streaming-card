# Hermes Feishu Streaming Card V4.2.10

[中文](release-notes-v4.2.10.md) | [English](release-notes-v4.2.10.en.md)

V4.2.10 收口仓库审查中确认的两个运行时缺口：非回环 sidecar 的交互回调/结果读取此前只依赖应用层 token，交互卡显示 timeout 但 sidecar 未强制执行截止时间。本版同时补齐跨平台 CI 和基础安全自动化。

## 修复内容

- **独立 sidecar 请求鉴权**：`sign_sidecar_request(...)` 与 `SidecarRequestProofVerifier` 使用 `hfc-sidecar-request-v1` 域，把 HTTP method、规范 path 与 raw body 一起签名。启用非回环事件认证时，`/card/actions`、`/interactions/{id}`、`/messages/{id}/summary` 在解析或返回状态前验签。
- **绝对交互截止时间**：sidecar 收到 `interaction.requested` 时记录 `requested_at` 并计算 `expires_at`。按钮、form submit、result poll 与周期清理在现有 session lock 下执行同一幂等过期转换。
- **晚到回调拒绝**：过期 interaction 进入 `failed`，返回“交互已过期”，并 PATCH 原卡；直连按钮和多选/自定义回答表单都不能把它改回 completed。
- **Gateway 超时收束**：poll deadline 到达后只 best-effort 发送一次新的 `interaction.failed`；不重放原始 `interaction.requested`，发送失败保持 fail-open。
- **清理不再永久阻塞**：只有尚未到期的 pending interaction 阻止 retention cleanup；周期循环先转换/刷新过期状态，再执行普通清理。

## CI 与安全门禁

- Ubuntu 全量 pytest 覆盖 Python 3.9、3.10、3.11、3.12，macOS 3.12 运行全量 pytest。Windows 3.12 运行固定的 portable runtime/server 套件，以及独立的 PowerShell installer 和迁移契约；依赖 POSIX `dir_fd`、mode bit、systemd 或 bash 的测试保留在 POSIX runner。
- 保留 Feishu SDK compatibility、PowerShell installer 与 Docker Compose runtime smoke。
- `actions/checkout v7.0.1`、`actions/setup-python v7.0.0` 和 `github/codeql-action v4` 均核验为 Node 24 runtime，并固定到 40 位不可变 commit SHA。
- 新增 CodeQL Python push/PR/weekly 扫描，以及 pip/GitHub Actions weekly Dependabot。

## 兼容与安全边界

- 默认 loopback 部署保持兼容；没有有效 transport root 时不会凭空生成 proof。
- callback token 与精确 chat binding 继续作为 defense in depth，不能替代网络请求鉴权。
- 缺失、过期、跨 method/path/body 与 replay proof 返回统一 401；响应与 `sidecar_request_auth_rejections` 不包含签名、标识符、正文或选择。
- 本版不修改 `legacy/`，不手工编辑 Hermes `gateway/run.py`，也不扩大 patcher 所有权范围。

## 升级

macOS / Linux：

```bash
export HFC_VERSION=v4.2.10
bash install.sh
```

Docker：

```bash
export HFC_VERSION=v4.2.10
bash install-docker.sh
```

Windows PowerShell：

```powershell
$env:HFC_VERSION = "v4.2.10"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.10/install.ps1" | iex
```

升级后运行：

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## 验证边界

- session/lifecycle/render/hook 单元回归：`556 passed`。
- server/clarify 完整集成回归：`297 passed`。
- 固定 Windows portable runtime/server 清单（在本机等价执行）：`1272 passed`；精确 Windows runner 结果以 PR 门禁为准。
- CI workflow 契约：`16 passed`。
- 隔离 v4.2.10 runtime 完整 pytest：`2475 passed, 6 skipped`。
- 精确 merge SHA、tag 后 Release assets 与公共 tag 安装结果在发布流程完成后写入 Release。

预期 Release assets：

- `hermes-feishu-card-v4.2.10-macos.tar.gz`
- `hermes-feishu-card-v4.2.10-linux.tar.gz`
- `hermes-feishu-card-v4.2.10-windows.zip`
- `hermes-feishu-card-v4.2.10-checksums.txt`
