# Hermes Feishu Streaming Card V4.2.11

[中文](release-notes-v4.2.11.md) | [English](release-notes-v4.2.11.en.md)

V4.2.11 修复 Issue #202：`interaction.requested` 发送并提升新交互卡后，旧流式卡此前不会进入终态，可能永久保留“正在使用 clarify”或工具运行态。现在每张被替代的卡都会冻结成只读历史快照，只有最新交互卡继续接收选择与后续回答。

## 修复内容

- **旧卡接力快照**：新交互卡成功发送后，旧卡 Header 使用绿色完成模板，subtitle 与引用摘要统一显示“已转入交互卡片”。
- **内容完整保留**：快照保留请求前的正文、thinking、timeline、工具记录、附件和已完成的历史交互结果；清除临时工具预览与 runtime phase。
- **交互控件冻结**：连续 clarify/approval 时，旧卡不再保留 pending 按钮、interaction id 或 callback token；每轮只有最新卡可操作。
- **顺序确定**：旧卡 animation task 先 cancel 并等待退出，再执行最终 PATCH，防止延迟 animation frame 覆盖快照。
- **原卡配置不漂移**：detached snapshot 通过 canonical session key 读取原有 per-session title、status 和 text-size 配置，兼容 `turn_id` 与 topic/reply 会话。

## 失败与安全边界

- 新卡仍先发送。发送失败会恢复请求前 `CardSession`，旧 message id 与 animation 保持权威，同一事件仍可安全重试。
- 旧卡 PATCH 使用现有有界更新重试、`feishu_update_*` metrics 与脱敏 `last_update_error`；全部失败也不会撤销已送达的新交互卡或返回失败。
- callback token、chat/operator binding、绝对过期、sequence 幂等、topic/reply 路由、native gray-text suppression 均未改变。
- 本版不修改 `legacy/`，不手工编辑 Hermes `gateway/run.py`，也不扩大 patcher 所有权范围。

## 升级

macOS / Linux：

```bash
export HFC_VERSION=v4.2.11
bash install.sh
```

Docker：

```bash
export HFC_VERSION=v4.2.11
bash install-docker.sh
```

Windows PowerShell：

```powershell
$env:HFC_VERSION = "v4.2.11"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.11/install.ps1" | iex
```

升级后运行：

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## 验证边界

- Issue #202 RED/GREEN 回归覆盖旧卡 Header/summary、正文与工具保留、控件移除、连续交互、PATCH fail-open、animation 顺序及 `turn_id` card config。
- session/render/server/clarify 聚焦矩阵：`450 passed`。
- 隔离 v4.2.11 候选完整 pytest：`2478 passed, 6 skipped`；`git diff --check` 通过。
- 本地 sdist/wheel 构建通过；全新 venv 安装候选 wheel 后 package/distribution 均为 `4.2.11`，导入来自该 venv 的 `site-packages`，CLI help 正常退出。
- 精确 merge SHA、tag 后 Release assets 与公共 `site-packages` 安装结果在发布流程完成后写入 Release 与发布准备记录。

预期 Release assets：

- `hermes-feishu-card-v4.2.11-macos.tar.gz`
- `hermes-feishu-card-v4.2.11-linux.tar.gz`
- `hermes-feishu-card-v4.2.11-windows.zip`
- `hermes-feishu-card-v4.2.11-checksums.txt`
