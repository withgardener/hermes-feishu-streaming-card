# V4.0.3

V4.0.3 修复 issue #106 在 V4.0.2 后仍存在的 stale-hook 路径：用户升级 runtime 包并重启 sidecar/Gateway，但没有重新安装 completion hook 时，卡片回答仍会作为灰色原生正文再次发送。

## 根因

- V4.0.1/V4.0.2 的 response 媒体裁剪位于新版 completion hook，需要重新执行 `install` 才能更新 `gateway/run.py`。
- V4.0.0 hook 仍能把完成事件发送给 sidecar，所以卡片正常更新；随后 Hermes `BasePlatformAdapter` 会先发送清理后的正文，再发送原生图片/文件，形成“卡片正文 + 灰色正文 + 媒体”。

## 修复

- 当 `message.completed` 包含原生媒体且 sidecar 明确返回已接管时，runtime 记录本次 chat 与卡片可见正文。
- Feishu adapter 的下一次 `send` 只有在 chat 和正文都精确匹配时才返回成功但不实际发送；状态只消费一次。
- `send_multiple_images`、`send_image_file`、`send_document`、`send_video` 与 `send_voice` 不变，媒体继续由 Hermes 原生通道投递。

## 安全边界

- 其他 chat、不同正文、之后再次出现的相同正文、非媒体完成、非飞书平台全部走原路径。
- sidecar 未接受、超时或失败时不登记抑制，完整原生 response 继续 fail-open。
- 新版 completion hook 仍优先在 response 层裁剪；本修复是旧 hook 的 runtime 兼容兜底。

## 贡献

- 感谢 @blakejia 升级 V4.0.2 后复测并提供截图，暴露 stale-hook 升级路径。
- 感谢 @ShakuOvO 最初报告 #106，感谢 @blakejia 在 Hermes `0.18.2` 上独立确认。

## 验证

- hook/patcher/install/server 热区矩阵：`513 passed`。
- 全量测试：`1269 passed, 3 skipped`；`git diff --check` 通过。
- 本地发布包：sdist/wheel 构建成功，干净 venv 从 `site-packages` 导入版本 `4.0.3`。

## Release assets

- `hermes-feishu-card-v4.0.3-macos.tar.gz`
- `hermes-feishu-card-v4.0.3-linux.tar.gz`
- `hermes-feishu-card-v4.0.3-windows.zip`
- `hermes-feishu-card-v4.0.3-checksums.txt`
