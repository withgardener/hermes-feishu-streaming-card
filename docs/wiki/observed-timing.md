# 观测耗时与 token 速率口径

开发分支在 `/health` 的 `timing` 中提供侧车受理事件的耗时统计，本地 `doctor --support-report` 保留同一组安全字段。默认卡片不增加统计行，也不为计时新增 PATCH。

| 字段 | 范围与条件 |
| --- | --- |
| `first_answer_total_ms` / `first_answer_samples` | 接受本轮 `message.started` 至首个确实增加可见回答的 `answer.delta`；每轮最多一个样本 |
| `observed_turn_total_ms` / `completed_samples` | 同一开始点至接受 `message.completed` 或 `message.failed`；包括工具、等待与调度 |
| `started_samples` | 当前仍保留在侧车会话内存中、有有效开始证据的回合数 |
| `window` | 固定为 `retained_session_memory`，清理旧会话或重启后会改变，不是累计全站指标 |
| `token_rate_status` | 当前为 `unavailable`，原因 `model_invocation_scope_missing` |

缺少开始事件、开始之前已经观察到其他活动、时钟倒退或时钟异常时不构造时长。没有流式答案的终局可以有总观测耗时，但没有首字样本。重复、乱序和终态后事件先遵守现有会话拒绝规则，不能重复记样本。计时使用 monotonic clock；显示恢复检查点不保存或恢复这些计时数据，重启不伪造开始点。

这不是模型 TTFT，也不代表客户端首字可见时间。它包含 HFC 受理事件之间的时间，无法替代模型、Gateway 和飞书 API 各自的耗时。Feishu 更新耗时和 terminal drain 指标仍沿用原来的独立口径。

[#392](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/392) 的 tok/s 需要同一模型调用的准确 token 数、开始/结束范围和重试归属。当前 completion tokens 有些来自累计值或文本估算，首末 delta 也可能跨越工具和多次模型调用，所以本轮明确报告不可计算，不把两组不对应的数据相除。后续取得完整调用证据后再添加有名称与范围的速率；不会把字符估算冒充模型生成速度。
