# V4.0.2

V4.0.2 是 V4.0.1 的安装升级热修。它保留 #106 的原生媒体正文去重修复，并允许经过完整证据验证的旧 owned hook 安全升级到当前 renderer。

## 修复内容

- 当当前 `run.py` 与 backup 均匹配 install manifest，owned markers 可完整移除且精确还原 backup，新版 hook 也能在内存中验证时，recovery planner 会执行 `reapply_current_hook`。
- 解决真实 V4.0.0 安装态升级时出现 `run.py changed since install; refusing to repair` 的问题。
- 用户编辑、current/backup hash 不符、backup 非法、markers 损坏或新版 anchors 不支持时，继续 fail-closed，不覆盖未知改动。

## 新增功能

- 实现 issue #107 的可选 `subscription_usage` footer。加入 `footer_fields` 后，插件通过 Hermes runtime 原生 `fetch_account_usage("openai-codex")` 显示 `5h 26% · weekly 89%` 风格的剩余额度。
- 默认不启用、不缓存账户数据、不在命令参数中传递凭据；旧 Hermes、未登录、网络错误或 5 秒超时均静默隐藏，不影响卡片完成。
- 感谢 @tianqiii 提出需求、Hermes 原生接口方案与展示格式。

## 同时包含

- V4.0.1 的 [issue #106](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/106) 修复：卡片成功后，原生通道只接收媒体指令，不再重复发送卡片已有的回答正文。
- 完成卡隐藏 `MEDIA:` 与内部本地路径，图片/文件继续由 Hermes 原生媒体通道投递。
- 感谢 @ShakuOvO 报告 #106，感谢 @blakejia 在 Hermes `0.18.2` 上独立确认。

## 验证

- recovery/install 回归矩阵：`121 passed`。
- server/render/subscription usage 聚焦矩阵：`237 passed`。
- 本机真实 V4.0.0 owned hook 升级：自动重应用当前 hook，doctor install state 完整一致，Gateway 与 sidecar 恢复运行。
- 本机 Hermes 原生 Codex account usage 只读验证：成功返回并格式化 Session/Weekly 两个窗口。
- 全量测试：`1266 passed, 3 skipped`；`git diff --check` 通过。
- 本地发布包：sdist/wheel 构建成功，干净 venv 从 `site-packages` 导入版本 `4.0.2`。

## Release assets

- `hermes-feishu-card-v4.0.2-macos.tar.gz`
- `hermes-feishu-card-v4.0.2-linux.tar.gz`
- `hermes-feishu-card-v4.0.2-windows.zip`
- `hermes-feishu-card-v4.0.2-checksums.txt`
