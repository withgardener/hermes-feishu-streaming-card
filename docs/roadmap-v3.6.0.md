# V3.6.0 Roadmap — 安装与运维产品化

[中文](roadmap-v3.6.0.md)

## 背景

截至 2026-06-04，GitHub open issues 为 0。V3.5.x 已经解决了卡片交互、流式顺序、长 Markdown、灰色原生消息和新版 Hermes 兼容等核心体验问题。

下一阶段的目标不是继续堆展示能力，而是把项目从“维护者能装好”推进到“普通 Hermes + 飞书用户能安装、诊断、修复和长期运维”。

## 目标

V3.6.0 的主命题是：**安装与运维产品化**。

做到以下标准才算完成：

- 新用户能通过一行安装或 Release 包完成安装，并能看懂失败原因。
- 老用户遇到 hook manifest、backup、`run.py changed since install` 等问题时，有明确 repair 路径。
- 媒体/文件类消息不再被错误塞进流式 Markdown 卡片。
- 多 profile / 多 bot 场景能通过 CLI 和 `/health.routing` 自助验证。
- CI 覆盖 Hermes 关键版本、安装脚本、Release 打包和 sidecar health 基础链路。

## 版本节奏

| 版本 | 定位 | 核心交付 |
|------|------|----------|
| V3.5.2 | 安装补丁版 | 修安装脚本边界、补 Release assets、更新安装文档 |
| V3.6.0 | 运维产品化版 | repair/diagnostics、媒体文件处理、多 profile CLI、health routing、E2E 矩阵 |
| V3.7.0 | 使用体验版 | 卡片折叠、工具详情、群聊策略、可观测性面板和重试操作 |

## V3.5.2 补丁范围

**动作**

- 更新 `CHANGELOG.md`、README 和 Release notes，说明一行安装、Release 包、checksum。
- 发布 tag 后验证 `.github/workflows/release-assets.yml` 能上传 macOS/Linux/Windows 安装包。
- 保留 `install.sh` 对 `.env` 白名单解析和 externally managed Python 的处理。
- 补 Windows PowerShell 的最低语法验证路径，至少在 CI 或文档里说明验证方式。

**验收**

- `curl ... install.sh | bash` 在 macOS 临时 Hermes fixture 上能跑通。
- Release 页面有 `macos.tar.gz`、`linux.tar.gz`、`windows.zip` 和 checksum。
- 相关文档测试和全量测试通过。

## V3.6.0 主线任务

### P0：安装自救与诊断

**要解决的问题**

真实用户最容易卡在 hook 历史状态：manifest 不一致、backup 不完整、`run.py changed since install`、Hermes 升级后旧 patch 残留。当前安装器为了安全会拒绝覆盖，这是正确的，但用户缺少下一步。

**动作**

- 新增 `doctor --explain`：把检测结果翻译成用户可执行步骤。
- 新增 `doctor --json`：输出机器可读诊断，便于 issue 模板和自动化。
- 新增 `setup --repair` 或 `repair` 子命令：只处理项目拥有的 patch/manifest/backup 状态，不静默覆盖用户改动。
- 对安全拒绝场景输出三类建议：可自动修复、需要人工确认、必须备份后手动处理。

**验收**

- fixture 覆盖干净安装、重复安装、Hermes 升级、manifest mismatch、backup missing、用户手改 `run.py`。
- 遇到 `run.py changed since install` 时，CLI 输出明确说明原因、风险和下一步命令。
- repair 不会破坏用户手动改动；不可判定时仍然 fail closed。

### P0：媒体/文件消息处理

**要解决的问题**

图片、文件、语音等非文本消息不适合进入流式 Markdown 卡片。它们应该由 sidecar 识别后走飞书原生媒体/文件发送，同时在卡片里保留摘要或链接。

**动作**

- 梳理 Hermes event 中附件、文件、图片、媒体字段来源。
- 在 session 层区分 text、summary、native media delivery。
- 对飞书原生发送失败提供安全 fallback，不重复刷灰色文本。
- 文档说明当前支持的媒体类型和限制。

**验收**

- 图片/文件不会破坏流式卡片正文。
- 飞书端能看到原生文件或媒体消息。
- 卡片内能看到附件摘要和发送状态。

### P1：多 Profile 运维能力

**动作**

- `smoke-feishu-card` 支持 `--profile-id`。
- `bots test` 支持 profile 维度和绑定检查。
- `/health.routing` 按 profile 分组展示 bot_count、chat_binding_count、last_route。
- README 增加多 profile 排障清单。

**验收**

- 用户能确认某个 profile 使用哪个 bot、哪个 chat binding。
- 多 profile 配置错误时能看到具体 profile 的缺失项。

### P1：E2E 与发布矩阵

**动作**

- 覆盖 Hermes `v2026.4.23`、`v2026.5.7`、`v2026.5.16+`、`v2026.5.29`、`0.13.x`、`0.14.x` 的 fixture/smoke。
- CI 验证 Release 打包 workflow 的 dry run。
- macOS/Linux 跑 `install.sh` dry run；Windows 至少跑 PowerShell parser 或 GitHub Actions Windows job。
- 增加真实 Feishu smoke checklist，不把真实凭据放入 CI。

**验收**

- 版本兼容失败能在 PR 阶段发现。
- Release 包构建失败不会等到人工发版时才发现。

## V3.7.0 候选体验增强

- 卡片思考过程折叠/展开，默认只展示最终答案和关键工具状态。
- 工具调用详情支持点击查看参数摘要、耗时、失败原因。
- 卡片内提供“继续”“重试”“取消”等操作入口，和 Hermes 交互能力对齐。
- 群聊规则支持 @机器人触发、白名单、chat binding 自动提示。
- 可观测性补充 update queue length、coalesce count、terminal drain latency、Feishu API latency。

## 风险与控制

| 风险 | 控制方式 |
|------|----------|
| repair 误覆盖用户改动 | 只修项目拥有的 patch；不确定就 fail closed；输出备份路径 |
| 飞书媒体 API 权限不足 | doctor 检测权限/配置；媒体失败时卡片提示原因 |
| Windows 安装验证不足 | 增加 Windows CI job 或至少 PowerShell parser 检查 |
| 卡片 UX 变复杂 | V3.6 先做运维稳定，V3.7 再做体验增强 |
| Hermes 继续快速变更 | 扩展 fixture 矩阵，doctor 输出 anchor 级别诊断 |

## 复盘指标

- 安装失败 issue 数量和类型。
- 用户从一行安装到 `status: running` 的成功率。
- repair 命令能自动解决的问题占比。
- 媒体/文件消息成功投递率。
- 流式卡片完成后灰色原生消息溢出次数。
- 版本发布后 7 天内新增兼容性 issue 数。
