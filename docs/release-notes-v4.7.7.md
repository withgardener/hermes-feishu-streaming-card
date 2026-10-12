# V4.7.7：表格内容完整保留

本版接入 PR #391 的可选原生表格，并修复合并前发现的长单元格截断问题。`card.native_tables` 默认 `false`；启用后，普通正文表格使用原生列宽与自动行高。

- 任一规范化表头或单元格超过 1,200 字符，整表回退完整 Markdown；不再用省略号替换尾部，其余合格表格仍可转换。
- Markdown 分段遇到无法拆开的长表头或行，保留整表，不再只显示“已折叠”。最终卡片仍受共享字节、元素和表格预算约束，超限进入既有完整内容交接。
- 默认关闭原生转换；profile/bot 可覆盖配置，调整后需重启 sidecar。旧客户端的原生组件显示能力不同，默认 Markdown 路径仍可使用。

回归覆盖 1,199/1,200/1,201/5,000 字符、中文与 ASCII、表头与数据、classic/task 展示、原生与 Markdown 混排及超大表格完整交接。完整 CI、精确合并提交、发布资产与普通公开包安装仍为发布门禁；真实平台与客户端验收结果单独记录，不以单元测试代替。

感谢 [ywarmy](https://github.com/ywarmy) 的 [PR #391](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/391) 原生表格实现与 CardKit API 验收证据；保留原始代码作者与历史贡献记录。

真实飞书 CardKit 创建/更新通过；飞书 8.1.17 桌面浅色/深色验收确认原生表格可读、超长 Markdown 单元格可滚动到完整尾标。5,000 字符表头通过 API 校验。Android/iOS 和新的 Gateway/model 端到端轮次未验证，详见[验收记录](reviews/2026-10-12-native-tables-acceptance.md)。

本次已获明确授权按桌面/API 范围发布，原生表格默认关闭，Android/iOS 未验证。另修正单列和七列以上的列宽分配，所有支持列数的宽度合计均为 100%。
