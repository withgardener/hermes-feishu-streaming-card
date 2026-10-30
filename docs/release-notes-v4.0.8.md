# V4.0.8

V4.0.8 修复 Issue #127：普通对话可以正常发送文件，但 cron 定时任务的完成卡只显示附件文件名、没有上传真实文件。

## Cron 附件投递

- 根因是旧 cron hook 在 `_deliver_result(...)` 入口发送卡片并立即返回，执行顺序早于 Hermes 的 `BasePlatformAdapter.extract_media(...)`，因此 `media_files` 从未生成。
- 新 hook 锚定在媒体提取和安全过滤之后。卡片成功且存在 `media_files` 时，插件只清空 `cleaned_delivery_content`，继续执行 Hermes 原有平台上传、topic 路由和失败处理。
- 没有附件时仍由卡片独占正文并结束原生投递；sidecar 失败时保持 fail-open，Hermes 原投递完整执行。
- `build_cron_event(...)` 现在识别 Hermes 的 `(path, is_voice)` 媒体元组，保留附件摘要并标记 `native_delivery=required`。
- `/health` 的附件诊断记录真实 `native_delivery` 策略。

## 升级安全

- V4.0.7 已安装的旧 cron hook 会从函数入口安全迁移到 `media_files` 过滤后的新锚点。
- 新旧 hook 都保持 marker 校验、幂等、精确移除和未知修改拒绝边界。
- 不具备 Hermes 媒体提取锚点的旧布局继续使用原有 fallback，不强行安装不安全的附件路径。

## 贡献

- 感谢 @zyq2552899783-lgtm 报告 #127，并清楚区分普通对话可发送文件、定时任务只显示文件名的行为差异。

## 验证

- 新增 cron `media_files` 事件、卡片正文/原生附件职责分离、V4.0.7 hook 迁移和附件诊断回归测试。
- 聚焦 hot-file 矩阵：`556 passed`。
- 完整发布 gate：`1328 passed, 3 skipped`，`git diff --check` 通过。
- 真实 Hermes 0.18.2 安装迁移与 `doctor --explain` 通过；cron hook 位于 `media_files` 安全过滤之后。
- 真实飞书 no-agent 一次性 cron 同时产生完成卡和独立文件消息；下载回来的文件与源文件字节一致，`cron_fallbacks=0`。
- sdist/wheel 构建成功，wheel 在干净 Python 3.12 venv 中导入为 `4.0.8`。公共 tag、assets 和 tagged installer 作为发布后的最终门禁。

## Release assets

- `hermes-feishu-card-v4.0.8-macos.tar.gz`
- `hermes-feishu-card-v4.0.8-linux.tar.gz`
- `hermes-feishu-card-v4.0.8-windows.zip`
- `hermes-feishu-card-v4.0.8-checksums.txt`
