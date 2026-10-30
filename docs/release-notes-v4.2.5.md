# Hermes Feishu Streaming Card V4.2.5

发布日期：2026-08-02

V4.2.5 是一次审查驱动的安全热修，修复 quoted turn 隔离、维护更新恢复、诊断建议、安装器版本解析与公开模板一致性，并为 Release Assets 增加精确 tag/commit 测试门禁。

## 审查问题与修复映射

- **HFC-REV-20260801-01**：使用 canonical `turn_id` 隔离 quoted turn，防止前一轮迟到 terminal 完成后一轮；缺少显式 ID 的 legacy producer 继续使用 alias fallback。
- **HFC-REV-20260801-02**：重复 maintenance resume 现在合并为同一运行，不修改 journal、一次性 credential 或 drain fence。
- **HFC-REV-20260801-03**：所有 maintenance 命令都绑定到已确认的 Hermes checkout、runtime、cwd 与环境，不再受 PATH 中其他 Hermes 安装影响。
- **HFC-REV-20260801-04**：quoted turn 的首个 non-terminal delta 不再被旧 sequence 去重状态误丢弃。
- **HFC-REV-20260801-05**：card/native delivery policy 在 canonical turn identity 上固定整轮，策略变更从下一轮生效。
- **HFC-REV-20260801-06**：maintenance resume 在 readiness 前按持久化 phase 对齐 external drain；post-restore phase 会先清除 drain。
- **HFC-REV-20260801-07**：doctor 只在 recovery/integrity plan 共同验证可执行时建议 `acknowledge-review`；其他 manual-review reason 先修复安装状态再复诊。
- **HFC-REV-20260801-08**：三端安装器的 `latest` 必须解析为稳定 `vX.Y.Z` tag，否则在 pip/setup 前退出；不再隐式回退 `main`。
- **HFC-REV-20260801-09**：公开 `config.yaml.example` 的版本标记与 package metadata 保持一致。

## Release hardening

Release Assets 只接受完整的、已注解的 `refs/tags/vMAJOR.MINOR.PATCH`。workflow 将 tag peel 到精确 commit，在该 commit 上运行 reusable 跨平台测试，并在构建前与上传前再次完整验证 tag、commit、`origin/main` ancestry 和五处版本标记。这是独立的残余风险控制，不是第十个审查 bug。

## 安装

```bash
export HFC_VERSION=v4.2.5
bash install.sh
```

`latest` 也会解析并固定到最新稳定 tag；若 Release API 不可用，请显式设置 `v4.2.5`，不要依赖隐式 `main`。

## Release assets

- `hermes-feishu-card-v4.2.5-macos.tar.gz`
- `hermes-feishu-card-v4.2.5-linux.tar.gz`
- `hermes-feishu-card-v4.2.5-windows.zip`
- `hermes-feishu-card-v4.2.5-checksums.txt`

下载后请按 checksums 文件核对 SHA-256。
