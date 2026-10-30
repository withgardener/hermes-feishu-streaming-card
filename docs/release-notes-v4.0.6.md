# V4.0.6

V4.0.6 集中修复 Hermes 0.18.x 的完成态、后台通知和升级恢复：流式任务不再因 completion hook 位于提前返回之后而卡在“生成中”，background process 与 `/background` 的运行/完成通知进入稳定飞书卡片；Hermes 真正替换源码后，也有显式、可验证且默认 fail-closed 的恢复路径。

## Hermes 0.18.x 完成态

- Issue #120 / PR #121：`message.completed` hook 会安装在 `agent_result.already_sent` 提前返回之前。
- terminal event 显式使用与 started/delta 相同的 reply anchor，避免终态落到模糊 fallback message id。
- queued completion hook 会在新版 `_stream_confirmed_final_delivery(...)` 多行调用之前回看合法 anchor，不再静默漏装。
- 旧 owned completion block 可识别并迁移；apply、AST parse、remove 与重复 apply 保持可验证和幂等。

## Background 通知卡片

- PR #119：background process 和 `/background` running/final envelope 统一转换为 `system.notice`。
- 同一后台任务使用稳定 notice identity，在同一张卡片更新运行态和完成态；并发任务互不覆盖。
- Hermes 即时返回的 `Background task started` 也由卡片 runtime 接管；带 reply anchor 的 background-task 使用独立 notice 生命周期，完成时原位收束，不再出现灰色启动回复或残留“生成中”。
- topic/thread 路由、Gateway sequence reset、重复任务输出、terminal retry/controller cleanup 都有明确边界。
- 卡片不可用时继续保持原生 fail-open，不把插件故障升级为 Hermes 主流程故障。

## Hermes 升级恢复

- Issue #118：`repair`、`install` 和 `setup` 新增 `--accept-hermes-upgrade`。
- 默认仍拒绝当前 Hermes 源码与已验证 backup 不同的状态；只有用户确认是有意升级并显式传入 `--accept-hermes-upgrade --yes` 才进入恢复。
- 恢复只清理经过校验的旧 HFC manifest/backup，不会用旧 backup 覆盖升级后的 Hermes 源码；随后以当前源码创建新 backup 并重新安装 hook。
- backup 缺失或损坏、manifest 无效、symlink、文件不可读、未知 marker、当前 anchors 不支持或仍有 owned patch 时继续拒绝。

## 贡献

- 感谢 @nasvip 提交 #118 的完整升级复现和拒绝信息。
- 感谢 @hzy 贡献 PR #119 的 background 通知卡片实现。
- 感谢 @lRoccoon 提交 #120 的生产诊断并贡献 PR #121。

## 验证

- 完整自动化发布 gate：`1315 passed, 3 skipped`；`git diff --check` 通过。
- #118 临时 Hermes sandbox：默认拒绝、显式接受、gateway+cron 升级与损坏 backup 拒绝共 6 条聚焦路径通过。
- sdist 与 wheel 构建成功；干净 Python 3.12 venv 从 wheel 导入 `4.0.6` 成功。
- 本机 Hermes 0.18.2 已完成 4.0.4 → 4.0.6 runtime 同步；`COMPLETE` 与 `QUEUED_COMPLETE` marker、runtime import 和 `doctor --explain` 均通过。
- 2026-07-15 真实飞书 E2E 通过：私聊 completion、私聊 `/background`、测试群聊 @bot completion、群话题 `/background` 均得到正确终态；话题路由留在原 thread，未产生灰色原生启动/答案，background 卡片终态不含“生成中”，sidecar 发送/更新失败均为 0。

## Release assets

- `hermes-feishu-card-v4.0.6-macos.tar.gz`
- `hermes-feishu-card-v4.0.6-linux.tar.gz`
- `hermes-feishu-card-v4.0.6-windows.zip`
- `hermes-feishu-card-v4.0.6-checksums.txt`
