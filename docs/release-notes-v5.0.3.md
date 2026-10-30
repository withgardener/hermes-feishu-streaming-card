# V5.0.3：Hermes 兼容、过期交互续答与可选生成速率

本版合并 [PR #438](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/438)、[PR #436](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/436) 和 [PR #430](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/430)，并补齐独立审查发现的边界。

## Hermes 源码兼容

[#437](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/437) 的安装拒绝来自 Hermes 新增 channel-pin 继承条件。安装器现在接受已核验的原表达式，以及 `event.internal or getattr(event, "inherit_channel_pin", False)`。来源、session/event 绑定、tuple 完整性、赋值顺序与 runner 参数仍须匹配；未知条件、缺失或重绑定继续拒绝安装。

上游矩阵按完整提交与文件摘要固定，main 为 `0ab43d4f67e41be75f4f6c0fa14a86dbcfd3e5b3`。支持检测、安装、重复安装、诊断和逐字节还原分别验证。这里的兼容结论针对固定源码，不代表所有后续 main 提交，也不等于真实 Gateway/model 执行验收。

## 交互过期后的输出位置

澄清或审批卡过期、Hermes 在下方改用原生文本提问后，后续思考、工具与答案会进入下方的续答卡。续答仍懒创建，没有新内容就不发送空卡。补充修复 sidecar 的扫描或事件入口先标记过期时遗漏续答边界的竞态。

重复失败、迟到完成及其他交互的事件不能重新激活旧授权；本轮结束时关闭未答交互不会产生额外续答。发送失败和内容超限继续经过已有 fallback 与完整内容交接。

## 可选的完成卡生成速率

在原有 `card.footer_fields` 列表中追加 `output_rate` 可开启 [#392](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/392) 第一阶段。默认列表不增加字段。

速率只取同一次 Hermes `post_api_request` 的 `usage.output_tokens` 与时间；多次调用的 token、窗口分别相加后相除，排除调用间工具与等待。流式窗口从上游首个有效流事件计至请求结束，包含上游可能的角色、reasoning 或生命周期事件，并非首个答案 token 后的纯解码速率。缺少首流事件时采用请求时长，可能包含 TTFT 和请求内重试；页脚明确标记近似口径。缺失、异常、过小、MoA 聚合或混合模型/供应方数据不显示，不从文本长度估算。

时间顺序、非有限数、极大整数及损坏检查点的速率值均有保护。数据继续放在既有 `tokens` 映射，不新增检查点字段。实际字段和显示标记见[观测口径](wiki/observed-timing.md)。运行中的流式估算不在本版范围。

## 安装与维护

沿用原 config、env、Hermes HOME 和服务管理方式，通过官方安装流程更新到 `v5.0.3`，参见[升级指南](upgrade-v4-to-v5.md)。版本默认值与双语文档同步。Ruff 更新至 0.17.1；官方 artifact 与 CodeQL Actions 固定至核验过的完整 commit SHA。Python 支持范围仍以包元数据为准。

## 验证范围

发布门禁包括独立失败复现、聚焦回归、固定 Git fixture 的完整 preflight、单独的上游固定源码矩阵、真实 hook 调用契约、Ruff/mypy、普通 wheel 子进程、安装/重复安装/还原、精确合并提交和 tag CI。发布后还核对四个官方资产、checksums 与隔离公开 tag 安装。

真实飞书 API、真实 Gateway/model、桌面视觉、Android 操作和 iOS 分别登记；自动化通过不代表客户端通过。#344 原始空正文问题仍缺少完整复现，#361 的真实后台长任务仍待独立证据，不能因本版相邻改动宣称全部解决。

## 贡献

感谢 [Lite-G](https://github.com/Lite-G) 贡献 #436、#437 / #438 的实现、报告和测试；感谢 [Thxzzzzz](https://github.com/Thxzzzzz) 贡献 #430 的过期续答修复；感谢 Dependabot 的 #388、#389、#390、#439。原始提交作者、Issue 证据署名与全部历史贡献记录保留在 Git 历史和两份 README 中。
