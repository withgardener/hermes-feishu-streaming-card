# V5.0.2：中文瞬态提示撤回修复

本版修复 [#434](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/434)：Hermes 使用简体中文语言包时，已知 busy 回执未进入 HFC 的自动撤回调度。可安装版本以 GitHub Release 的 tag 和资产为准。

## 修复范围

- redirect、interrupt、steer 及活跃子代理 steer 回执使用同一完整模板识别，同时覆盖固定上游的英文与简体中文文案，以及原生单行活动详情。确认发送成功后沿原 profile/chat/thread 调度 15 秒撤回。
- 中文裸 `⏳ 正在压缩上下文` 和其 `...` 形式沿用英文裸压缩提示的撤回策略。
- 收紧旧英文 redirect 的宽前缀判定，保留附加正文和 onboarding 指南。未知翻译、自定义文案或相似 emoji 不会被猜作可撤回通知。

文案与发送链依据 Hermes `e06df9c2eae6901f4c88f464e0ae6e753c0428b8` 的 `gateway/run_busy.py`、`locales/en.yaml` 和 `locales/zh.yaml`。本版不动态加载 Hermes i18n，也不声称支持所有语言包。

## 保留的行为

该上游修订的子代理 working 和压缩降级提示会附带消息已排队、稍后处理及 `/stop` 说明。这些完整消息保留，裸子代理 working 状态也没有新增到撤回清单。排队确认、onboarding、附加正文和未知内容继续可见。持续 Working 心跳仍由 Hermes 原地编辑并在终轮清理，HFC 不新增周期撤回。

原有 15 秒延迟、发送成功检查、路由身份、重复登记和删除执行边界不变。Python 支持范围、卡片布局和配置默认值保持不变。使用官方安装流程更新到 `v5.0.2`，保留原 config、env、Hermes HOME 与服务归属；参见[升级指南](upgrade-v4-to-v5.md)和[通知生命周期](wiki/notice-lifecycle.md)。

## 验证范围

修复候选 `74f409e` 已通过 focused **146 项**、本地完整回归 **6687 passed / 33 skipped** 及全部 **18 项 CI 检查**。本地跳过项包括 21 项单独启用的固定上游检查、1 项 PM fixture、6 项 SDK 检查（含 collection skip）、1 项 Windows sharing semantics 和 4 项 PowerShell 检查；这些不能被描述为本地已通过。候选 CI 另跑固定上游与平台门禁。

测试执行带 SHA/摘要的最小真实上游 compose 方法切片和生成的 busy send hook，覆盖中英文、活动详情、失败与保留文案；adapter 原生文本出口、真实回环 HTTP、重复调度及 default/work 路由也已验证。普通非 editable wheel 在独立 `-I` 子进程中执行新分类和 busy 入口，136 个包资源与候选源码逐字一致。5.0.2 元数据、精确 merge/tag、资产 checksum 和隔离公开安装按[发布手册](wiki/release-playbook.md)继续核验。

固定片段测试不是完整该版 Hermes/Gateway 执行。本次未新增真实飞书、桌面、Android 或 iOS 验收，不用自动化结果代替这些证据。

## 致谢

感谢 [Timeral](https://github.com/Timeral) 在 [#434](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/434) 提供中文环境复现、英文判定对照和源码定位。
