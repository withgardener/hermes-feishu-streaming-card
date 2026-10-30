# Hermes Feishu Streaming Card V4.2.9

发布日期：2026-08-09

V4.2.9 收口 Issue #197、PR #196 和 PR #199：引用已完成卡片时保留真实回答摘要，慢速 slash-confirm 不再卡住飞书回调，多选/自定义回答表单以严格鉴权方式进入正式版本。

## 修复与改进

- **引用回复上下文（Issue #197）**：已完成卡片的 `config.summary` 使用单行、最长 120 字符的回答摘录；进度接力、等待和失败状态继续显示状态摘要。
- **慢速命令确认（PR #196）**：slash-confirm 在飞书回调之外解析，随后 PATCH 原卡；PATCH 失败时发送 follow-up 结果卡。pending state 在调度前原子占用，调度被拒绝或抛错时同步回退，不丢点击也不重复执行。
- **多选与自定义回答（PR #199）**：clarify 卡片支持原生多选、带序号的单选按钮和 “Other” 自定义输入；等待期间冻结无关 PATCH，避免清空用户尚未提交的选择；footer 显示交互过期时间。
- **Hermes 兼容**：patcher 同时兼容带或不带 `multi_select` 参数的 clarify callback。

## 安全边界

- 表单按钮名只携带随机 callback token，不把 `interaction_id` 当作凭据。
- sidecar 只接受 callback token 完全匹配且 callback chat 非空、完全匹配的表单提交。
- `/events` 始终只 POST 一次；响应可能丢失时，只读查询 interaction 状态，不重放事件。
- interaction 日志不记录原始 ID、URL、用户选择、响应正文或 error 文本。

## 贡献者

- 感谢 @zayn-0101 提交 PR #196。
- 感谢 @Cassius0924 提交 PR #199。

## 安装

macOS / Linux：

```bash
export HFC_VERSION=v4.2.9
bash install.sh
```

Windows PowerShell：

```powershell
$env:HFC_VERSION = "v4.2.9"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.9/install.ps1" | iex
```

安装后运行：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
```

包内 Python import 应来自目标环境的 `site-packages`，package/distribution 版本均为 `4.2.9`。

## Release Assets

- `hermes-feishu-card-v4.2.9-macos.tar.gz`
- `hermes-feishu-card-v4.2.9-linux.tar.gz`
- `hermes-feishu-card-v4.2.9-windows.zip`
- `hermes-feishu-card-v4.2.9-checksums.txt`
