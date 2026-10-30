# V5 visual assets / 图片来源

- `readme-cover-v5.png`：使用原生 image_gen 生成的 V5 宣传封面。它是艺术视觉，不是产品截图。
- `feishu-v5-continuation-redacted.png`：基于 2026-10-15 桌面飞书实际“允许一次 → 续答”验收截图，经生成式工具去除聊天头像、姓名和引用身份信息。原验收者明确确认“查看续答”正确跳转。
- `feishu-v5-expiry-redacted.png`：基于同日桌面飞书实际 clarify 自然超时验收截图，经同样方式处理隐私区域。展示“已超时”、失效选项和本轮统计。
- `feishu-v5-clarify-receipts-redacted.png`：基于桌面飞书三次串行 clarify 的真实验收截图，提取单选、多选和自由文本的已提交回执，生成式脱敏后并排展示。保留实际返回值 `A`、`A, C` 和 `手机输入验收123`；这些是已提交状态，不是待操作表单。
- `feishu-command-approval-redacted.png`：基于早期候选的手机端 `/reload-mcp` 真实验收截图，只保留命令确认卡，移除聊天外框和身份信息。保留“允许一次”“始终允许”“取消”三个原始按钮。它说明命令确认流程，不代表当前模型工具审批卡的全部选项。

四张界面图经过生成式处理，可能存在局部字形、间距或排版差异，不作为逐像素原始截图或独立验收证据。原始图片、消息读回和执行审计保留在私有验收记录，不进入公开仓库。公开图片经人工对照关键状态、选项、结果、用时和 footer 后用于说明功能。

The cover is AI-generated artwork. Four interface images derive from real Feishu acceptance screenshots and use generative privacy redaction. The clarification composite shows submitted single-choice, multiple-choice and text-input receipts; it does not depict pending form controls. The command confirmation comes from earlier mobile acceptance, while continuation, timeout and clarification receipts come from desktop acceptance. They may differ locally in glyphs, spacing or layout and are illustrative, not pixel-exact originals or independent acceptance evidence. Private originals and execution evidence are retained separately. No private chat identity is included in these public assets.
