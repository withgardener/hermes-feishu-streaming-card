# V5.0.1：Hermes 0.22.x 接点兼容与 PM 持久依赖

本版修复 #428 的 completion/审批接点缺失，以及 #431 的 HFC 在 PM 环境换代后消失。可安装版本以 GitHub Release 的 tag 和资产为准。

## 修复内容

- 对固定 Hermes 源码 `297552a9d646119871391d202509822cd86330df`、`7bda2a3368024f7ae1c70cef16583e7c2c891674`，验证 handler 的 import、继承和 MRO 无遮蔽关系，在 `GatewayTurnPersistenceMixin` 的实际 owner 注入 completion。计时继续由原 handler 传入，不放宽未知源码检测。
- 支持 generation 检查后的 `_render_approval_sync` 接点。HFC 仍通过原 Hermes request handle 解析一次，原生 authority/viewer 顺序保留；等待期间代次失效会拒绝解析，不复活已结束审批。
- 已安装的 V4 manifest 增加这组已验证源码目标时，先验证旧备份与 ownership，再要求显式 `--accept-hermes-upgrade`。restore 恢复更新后 Hermes 源码的原始字节。
- PM 管理的安装通过官方 `hermes_cli.plugins_admission.admit_plugin_set_change` 登记 dependency-only member，缓存精确普通 wheel，并通过本地 `tool.uv.sources` 让下一代 workspace 继续安装相同字节。已能导入同版本也必须登记；登记后重新选择 committed venv，再校验安装来源与包资源。
- PM 登记、完成、回滚和移除使用同一安装锁。失败时只撤回本次拥有的变更，保留用户已有 selection、disabled 值及其他配置；未知提交状态保留诊断来源。restore 保留依赖，uninstall 在恢复 hooks 后移除 HFC 自己新增且未被修改的登记。

## 兼容与升级边界

这两个报告修订的安装检测为 `partial`：required completion/approval 已验证；拆出的 optional progress status callback，以及 `_run_sync_scoped` 的新增 provider/model 采集点不在本次补丁范围。它们保持原生或未知值处理，不宣称完整状态/统计覆盖，也不宣称任意 Hermes latest main 已受支持。其他固定源码矩阵保留原有范围。

使用原官方安装流程更新到 `v5.0.1`，保留原 config、env、Hermes HOME 和服务归属。不要手工编辑已安装的 Hermes 源码或 PM facts/lock。明确 disabled、未知目录归属、用户修改、依赖冲突或不确定文件状态会拒绝覆盖；参见[维护指南](wiki/maintenance-guide.md#hermes-022x-与-pm-依赖登记)及[升级指南](upgrade-v4-to-v5.md)。Python 支持范围、卡片默认值和原有交互权限不变。

## 验证范围

已覆盖固定源码安装、重复安装、doctor/integrity、旧布局迁移和逐字 restore；原 Hermes approval queue/controls 的一次解析、重复/迟到及代次变化；普通 wheel 在独立子进程中的导入与真实上游 PM engine 跨 generation 保留。最终 wheel 的 package resources 逐字对照源码，portable 分支另有故障注入。完整跨平台 CI、精确 merge/tag、资产校验和公开 tag 安装按[发布手册](wiki/release-playbook.md)执行。

PM 集成在私有 HOME 的最小 project 中注入现成 uv/Python 工具链，没有运行完整 Hermes dependency closure 或 PM worker transport。本次未新增生产 updater、真实 Gateway/model/飞书或 Windows 主机验收；现有自动化与源码兼容性不能代替这些证据。卡片布局没有改动，不新增客户端视觉通过声明。

## 致谢

感谢 [lanx214](https://github.com/lanx214) 报告 [#428](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/428) 与 [#431](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/431)，感谢 [za8209](https://github.com/za8209) 在 #428 提供 macOS 复现日志及源码定位。感谢 [Lite-G](https://github.com/Lite-G) 在独立 [PR #432](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/432) 提供同类兼容性分析与方案；该 PR 的代码未纳入本版。这些是 issue 证据与独立方案署名，不视为本版代码作者。保留此前 README、发行说明和 Git 历史中的全部贡献记录与原提交作者。
