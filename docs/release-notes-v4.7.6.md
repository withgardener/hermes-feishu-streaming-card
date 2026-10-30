# V4.7.6：分离 HOME 与多实例身份修复

源码安装在 `/usr/local/lib/hermes-agent`、数据放在 `/root/.hermes`，或多个 Gateway 共用源码时，HFC 此前可能正常发卡，却一直报告 `runtime_owner_unverified`。本版修复 #384，支持显式绑定源码与进程 HOME。

## 修复与使用

- `setup --hermes-home /实际/Hermes/HOME` 把绑定写入选定的 HFC `.env`；也可配置 `service.hermes_home`。安装、PM 解释器选择、启动检查和认证心跳沿用同一 HOME。普通 `HERMES_HOME` 不会覆盖侧车的显式绑定。
- 共享源码的不同 HOME 使用不同身份摘要。错误 HOME、旧的仅源码身份和重复心跳均不能接管；要求 Hermes 提供进程级 `get_process_hermes_home()`，不能以 task-local profile API 代替。
- `doctor --env-file` 和 `HFC_ENV_FILE` 读取与 setup 相同的绑定；显式 `--hermes-home` 冲突时在探测前拒绝，诊断不会写回配置。
- `integrity.last_reason` 保留脱敏后的 owner 原因，不再把 `runtime_owner_unverified` 等已知诊断变成 `unknown`。doctor 区分配置绑定和实际运行证明。
- 普通源码父目录布局保持旧身份；Docker 无凭据首装仍允许先安装 hook 再配置 Hermes。分离 HOME 须为包含 Hermes `config.yaml` 的绝对目录。
- 维护任务记录 HOME，配置改绑后旧任务拒绝执行。分离 HOME 或 `service.shared_source: true` 的实例在卡片更新前明确拒绝，要求终端维护；不会自行清除完整性围栏。

通过原安装入口升级 HFC，重新运行 setup，并通过原服务管理器重启 sidecar、Gateway 和 Desktop。每个独立 Gateway 使用独立 HFC 配置、env file、私有 state 和端口。多个 Gateway 共用源码时，所有 sidecar 都设置 `service.shared_source: true`，包括默认 HOME；升级公共源码前先排空所有使用者。本版不提供跨实例自动升级协调。

确认 `readiness=ready`、`generation_match=true` 与 `drain_home_verified=true`。配置示例与优先级见[用户指南](user-guide.md#程序目录与-hermes_home-分离)。旧版读取带 HOME 的新维护任务会拒绝；降级前应结束维护任务。

## 验证边界

回归覆盖配置保存与重载、PM 子解释器、签名 HTTP 身份隔离、重复心跳、重启和旧维护任务拒绝。普通 wheel 启动的两个 sidecar 子进程验证错误 HOME 被拒绝、正确实例恢复 ready；真实 Hermes v0.21.6 constants 子进程验证 task-local HOME 覆盖不会改变进程绑定。完整跨平台 CI、精确合并提交、发布资产和公开安装仍为发布门禁，结果随 GitHub Release 公布。

不修改卡片布局；未声称完成报告者 NAS/WSL 真机或真实飞书消息复测。上游兼容门禁固定到 Hermes v0.21.6（`818c13be1dc4`）和 main（`c57331677d7f`），不保证任意未来 main。

感谢 @lanx214、@Lite-G、@7360403-coder 提供分离目录、共享源码 profile 与 NAS Docker 的现场证据。保留此前贡献者与历史版本记录；本次反馈不作为代码作者署名。
