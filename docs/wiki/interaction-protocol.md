# 交互责任与提交顺序

Hermes 原 runtime handle 和它的锁负责唯一执行选择及 consumed 状态。HFC 负责交互卡投递和展示结果。`RuntimeCallbackSnapshot` 只绑定原显示窗口，`RuntimeInteractionDeliveryReservation` 只占位待送达的卡片；两者都不恢复执行，也不产生第二套授权 claim。

## 责任归属

| 职责 | 实现所有者 |
| --- | --- |
| callback/form/choice 输入表示 | `interaction_input` |
| identity 拒绝顺序、期限、暂停窗口资格、文本政策与容量预演 | `interaction_rules` |
| 原 resolver 的单次认证请求与有界完整响应 | `interaction_resolver` |
| 静态脱敏回执投影 | `interaction_receipts` |
| pending 输入冻结、当前 owner 与辅助回执选择 | `owner_display_policy` |
| 展示状态转换 | `session.CardSession` / `InteractionState` |
| 注册表、session lock、投递事务和 HTTP 映射 | `server` |
| 终态 PATCH/retry/recover | `terminal_delivery` |
| 实时 registry/controller 清理 | `lifecycle.CleanupState` |

## 请求受理与送卡

1. 在原 session lock 内核对事件身份与 sequence，执行容量预演和真实状态 apply，登记原 owner 的 runtime delivery reservation。占位只保留这一张待投递卡的事务，不提前承诺送达。
2. 锁外 send 使用原 chat/profile/topic、reply anchor 和稳定 delivery key。重试政策由现有 transport 决定，不重放 `interaction.requested`。
3. 重新取得原锁，比较 reservation、session 和 interaction 的对象身份；还须匹配 pending 状态、admission fingerprint 及 sequence。只有确认送达且比较成立，才能 store 并释放这个 reservation。
4. 锁外 finalize 原前一卡，保留其方言和完整内容。失败或 owner 已替换时按下表处理，不能用复用 key 找到的新对象承接旧事务。

`_complete_runtime_interaction_delivery` 保留为原 owner 的 compare-and-commit。send 结果、实时 identity 和 rollback 要在同一个事务中衔接；已有规则模块负责独立资格判断，无需新增布尔枚举层、claim registry 或 resolver。

| 平台送达确认 | 原 owner 比较 | 状态动作 | HTTP |
| --- | --- | --- | --- |
| 是 | 成立 | store 原交互结果，释放原 reservation，再 finalize 前一卡 | 200，`applied=true`、`runtime_admission=true` |
| 否或不确定 | 成立 | 恢复原 rollback snapshot，只释放原 reservation | 502，发送失败 |
| 否或不确定 | 不成立 | 不回滚新 owner；仅清仍匹配的原 admission/原 reservation | 502，发送失败 |
| 是 | 不成立 | 不向新 owner 提交旧交互；仅清仍匹配的原 admission/原 reservation | 409，投递状态已变化 |

“仅清原 admission”要求当前 interaction 仍是原对象且 fingerprint 匹配。“仅释放原 reservation”要求 registry 中仍是这一对象，不能按 key 无条件 pop 后继事务。送达确认不是执行授权，也不能把未知结果当成确认。

## callback 与原执行选择

callback 输入解析后，server 在原锁内重查 owner/id/token/chat；身份拒绝先于 delivery_pending。检查到期状态和 runtime profile 后冻结 `RuntimeCallbackSnapshot`，锁外只调用一次既有 resolver。原 runtime handle 决定选择是否被消费。

resolver 返回后，server 再取同一锁，复核原对象与 fingerprint，并再次检查期限；随后按当时 `last_sequence + 1` 构造内部完成事件，以 `advance_sequence=False` 提交。callback 不能推进 Hermes `/events` 序号。响应卡在锁内保存，后台 PATCH 不延长原 callback 的提交事务。

需要敏感请求 proof 时，认证失败返回 401。输入解析失败返回 400；找不到匹配身份/profile 返回 404；投递占位、已完成、已过期或 resolver 后的 owner/fingerprint 变化返回 409；resolver 不可用返回 503 并保留原失败语义。成功返回 200 和结果卡。取消继续传播。HTTP 状态映射不授予执行权；resolver 不自动重试，callback response 丢失也不允许重放原请求来恢复授权。

## paused、expiry 与回执

暂停窗口续期仍在原锁内核验 owner、interaction、token、chat 和 approval kind。`ApprovalWindowState` 要求原 pausable waiter 仍新鲜，并拒绝旧 native admission。合格窗口旋转 token，重新显示完整审批范围；下一次明确选择才走原 handle。runtime 消失或授权过期时只返回失效说明，不能复活旧任务。

期限转换由 `InteractionState.expire` 和 runtime deadline 规则决定。server 记录展示结果，锁外更新原辅助回执；每次写回继续核验原 interaction、owner 与 sequence。只有完整回执 PATCH 得到确认且 fingerprint 仍一致，才精简前一卡的重复范围。

pending/paused 的普通流式更新和动画应冻结输入；交互生命周期及终态按既有规则处理。恢复检查点只保留脱敏静态回执，不恢复 callback token、执行 handle 或 admission。原 GET 结果缓存用于展示确认和 waiter freshness，不能据此推断旧执行已恢复。

## 保留协调的理由

`_interaction_action`、`_resume_paused_approval`、`_complete_runtime_interaction_delivery` 及 expiry/store helpers 可以保留原锁、registry mutation、配置读取和 HTTP 映射。它们连接同一 owner 的真实时点；把这些步骤换文件或放进一个新 service 并不会增加独立执行权证明。结构验收看唯一 owner、规则归属及锁前后顺序，不能以仍有 if/app 或函数较长判断未完成。

## 关键测试与最终候选绑定

下列现存测试节点均为 **需最终候选证据绑定**。最终记录必须包含准确源码/测试 SHA、命令、结果及 source/wheel/平台范围；本表不沿用历史通过数冒充当前候选。

| 合同 | 实际测试节点 |
| --- | --- |
| 原 handle、错误绑定/过期/已消费拒绝 | `tests/unit/test_runtime_interaction_transport.py::test_real_callback_invokes_exact_resolver_and_wakes_original_wait`；`tests/unit/test_runtime_interaction_transport.py::test_callback_rejects_wrong_binding_expiry_conflict_and_consumed_reopen` |
| 实际送达才受理、canonical replay | `tests/integration/test_server.py::test_runtime_interaction_admission_requires_actual_delivery_and_canonical_replay` |
| 原 snapshot rollback、send 不持 session lock | `tests/integration/test_server.py::test_runtime_interaction_delivery_failure_rolls_back_fence_for_exact_retry`；`tests/integration/test_server.py::test_runtime_interaction_feishu_delivery_holds_no_message_lock` |
| 一次 resolver、并发选择与完成时点 | `tests/integration/test_server.py::test_runtime_interaction_action_resolves_listener_before_terminal_mutation`；`tests/integration/test_server.py::test_runtime_interaction_concurrent_same_and_conflicting_actions_complete_once_without_lock` |
| resolver 失败、IO 中到期、owner 替换 | `tests/integration/test_server.py::test_runtime_interaction_callback_failure_keeps_pending_and_hides_descriptor`；`tests/integration/test_server.py::test_runtime_interaction_expiry_during_blocked_callback_erases_admission`；`tests/integration/test_server.py::test_runtime_interaction_session_replacement_during_callback_clears_old_admission` |
| identity 在占位前、exact deadline | `tests/unit/test_interaction_rules.py::test_callback_rejection_keeps_identity_before_reservation`；`tests/unit/test_interaction_rules.py::test_runtime_deadline_exact_types_inclusive_boundary_and_short_circuit` |
| 容量拒绝不修改/注册真实 owner | `tests/unit/test_interaction_preflight.py::test_existing_owner_is_deeply_isolated_and_sequence_policy_reaches_apply`；`tests/integration/test_server.py::test_oversized_interaction_declines_before_claiming_or_sending` |
| 暂停后需新明确选择、runtime 消失拒绝 | `tests/integration/test_server.py::test_expired_approval_pauses_then_requires_fresh_explicit_consent`；`tests/integration/test_server.py::test_paused_approval_after_runtime_disappears_explains_expiry_without_consent` |
| 原 UUID/代次通知恢复 | `tests/integration/test_server.py::test_paused_approval_notification_recovers_with_same_uuid` |
| 不重置 pending 输入、回执与终态互不阻塞 | `tests/integration/test_card_freeze.py::test_streaming_events_do_not_update_card_while_interaction_pending`；`tests/integration/test_interaction_continuation.py::test_terminal_ack_and_answer_do_not_wait_for_receipt_or_repeat_its_patch` |
| 方言和先 render 再选当前卡 | `tests/integration/test_interaction_continuation.py::test_resolved_receipts_keep_dialect_choices_and_live_turn`；`tests/integration/test_interaction_continuation.py::test_failed_receipt_render_is_read_only_before_owner_policy_selection` |
| 不消耗 transport sequence | `tests/integration/test_interaction_continuation.py::test_native_runtime_selection_reaches_new_owner_without_consuming_transport_sequence` |

这份责任映射确认保留原 compare-and-commit，不新增实现层。最终候选还需绑定完整回归、普通包和适用平台证据；真实客户端点击、移动端、五人上手及完整 V5 仍各有验收范围。
