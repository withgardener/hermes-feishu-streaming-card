# V4.1.4 发布说明

[English](release-notes-v4.1.4.en.md) | [中文](release-notes-v4.1.4.md)

V4.1.4 修复 Issue #171 报告的 Windows 旧版安装迁移缺口：当旧版 owned hook 与备份仍在、但 `.hermes_feishu_card_manifest` 缺失时，官方 `install` / `setup` 可以在严格验证后重建 manifest，并升级到当前 hook。

## 修复内容

- manifest 缺失且 gateway backup 存在时，安装器只在 `remove_patch_lenient(current) == backup`、backup 是可解析的干净源码、目标不是 symlink 时接受旧版 owned hook。
- optional Cron 与 required exact Base 使用各自的严格 patch removal 验证；当前文件必须逐字还原到对应 backup。旧版没有 Base hook 时，安装器会按当前 Hermes 检测结果补建 Base backup、注入 hook，并写入 `manifest_version: 2`。
- 该迁移走 install 流程的 Windows portable 写入序列，而不是 Windows 不支持的 directory-fd recovery 事务；已有目标在独占 handle 持有期间完成读取校验、写入、刷盘与复验，owned rollback 也受 identity + digest snapshot fence 约束。若失败后无法安全删除本次新建的 evidence，则保留现场并要求人工复核。
- `--no-repair` 继续禁止自动修复。owned marker 之外的用户改动、校验后的并发编辑、backup 不一致、缺失目标、symlink 或不可解析源码继续 fail-closed，不会被自动覆盖。

## 根因说明

公开 v4.0.14 的官方 CLI 会创建 manifest；Issue #171 中的 manifest 缺失表示本地安装证据已不完整。实测 Unicode 注释、CRLF 与 Windows 原生相对路径本身不会造成 `ast.parse`、文本 hash 或路径比较失败。真正阻断是：v4.1.3 将旧版生成的 owned block body 视为 marker 异常，而通用 recovery 事务在 Windows 上按安全设计不可执行。

不要手工创建 manifest，也不要直接调用内部 `apply_patch()`。V4.1.4 只从现存源码与 backup 推导可验证迁移。

## 升级与复测

```bash
export HFC_VERSION=v4.1.4
hermes-feishu-card doctor --config CONFIG --hermes-dir HERMES_DIR --explain
hermes-feishu-card install --hermes-dir HERMES_DIR --yes
```

Windows PowerShell 使用官方 `install.ps1` / `setup` 流程并指定 `v4.1.4`。成功时应看到 `manifest: rebuilt` 与 `install ok`；随后重启 Hermes Gateway，再确认 doctor 的 install state 为 `installed`。

仓库自动化覆盖无 directory-fd 的 Windows 等价分支、Windows 独占 handle、`--no-repair`、Cron/Base 目标缺失、owned block 外用户改动，以及写入/rollback 前并发编辑的拒绝分支；隔离的公开 v4.0.14 `site-packages` 样本另行覆盖普通 Gateway、Hermes v0.19.0 required exact Base、optional Cron 与 Unicode + CRLF。报告者真实 Windows 验收仍待确认；正式发布仍以完整 pytest、CI、exact merge SHA、wheel/sdist、隔离 `site-packages` 安装和 Release assets 为门禁。
