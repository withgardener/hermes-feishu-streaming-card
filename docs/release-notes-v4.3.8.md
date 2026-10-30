# Hermes Feishu Streaming Card V4.3.8

[中文](release-notes-v4.3.8.md) | [English](release-notes-v4.3.8.en.md)

V4.3.8 修复安装后的开机常驻、batch clarify 连续提问竞态和 Feishu/Lark HTTP proxy 三个运行可靠性问题，同时保持 sequence、service ownership 与本机网络隔离边界。

## 修复内容

- Issue #244：引导式 `setup` 在 Linux systemd user manager 可用且 linger 已开启时，默认启用 HFC ownership 保护的 persistent service。能力不可用时会明确警告 sidecar 无法跨主机重启存活，启动现有 transient 路径，并给出精确 `enable` 命令；`setup --transient` 可显式退出自动常驻。
- Issue #245：认证 card action 生成的内部 `interaction.completed` 不再推进 Hermes `/events` transport 的 `last_sequence`。batch clarify 点击第一题后，使用相同下一序号到达的第二个 `interaction.requested` 会被正常接受；第一题 callback card 也会在 session lock 内快照，不混入第二题。
- PR #242：远程 Feishu/Lark HTTP 请求会遵循标准 proxy 环境变量；loopback、private、link-local 与 unspecified 目标继续绕过环境代理，避免本机 sidecar、mock 与验收流量意外外送。
- CLI `status` 的集成测试改用独立 config 与 state dir，不再读取维护者本机正在运行的 sidecar 状态。

## 安全边界

- `setup` 不会自行执行 `loginctl enable-linger`、调用 sudo、进入 system manager 或写 `/etc`。persistent 能力不完整时只使用原有 transient fallback。
- transport event 继续执行严格单调 sequence 校验；只有通过既有认证和 interaction identity 校验的 out-of-band card callback 不推进 transport watermark。
- persistent unit/manifest ownership、SHA-256 对账、safe stop、drift 拒绝和 `disable` 清理契约不放宽。
- proxy 支持不改变 Feishu API payload、callback authentication、card ownership、delivery UUID 或归档 `legacy/` runtime。

## 验证状态

- proxy client 单元与真实本机 HTTP proxy integration：**已通过（`81 passed`）**。
- session/hook/server batch clarify 与 sequence 回归：**已通过（`937 passed`）**；新增确定性竞态用例覆盖第一题 callback 与第二题 `/events` 并发。
- persistent/process/install 聚焦矩阵：**已通过（`649 passed, 5 skipped`）**；fresh normal-wheel 进程生命周期测试：**`8 passed`**。
- fresh Python 3.12 normal-wheel 环境完整 pytest：**`3343 passed, 6 skipped in 690.84s`**；`git diff --check`：**通过**。release PR CI、exact merge SHA、annotated tag、public tagged install 与 Release assets/checksums 以最终发布门禁为准。
- 真实 Feishu/Lark 客户端 smoke：**未执行**。真实 Linux systemd user + linger 主机 smoke：**未执行**；自动化、mock 与 CI 不冒充真实平台验收。

## 致谢

感谢 [nasvip](https://github.com/nasvip) 在 Issue #244 提供主机重启后 sidecar 静默离线的生产问题与安装体验建议。

感谢 [Timeral](https://github.com/Timeral) 在 Issue #245 提供 batch clarify 连续提问的竞态窗口与可复现时序。

感谢 [PureWhiteWu](https://github.com/PureWhiteWu) 实现 PR #242 的 proxy 环境支持与回归测试；其原始代码作者归属已保留在 Git history。
