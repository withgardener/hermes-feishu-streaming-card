# V4.0.12

V4.0.12 处理 Issues #133 和 #136：Hermes 上下文压缩不再是卡片静默空窗，五类卡片文本可以按 PC/mobile 配置字号，sidecar 也不会再把缺凭据的 Noop 投递伪装成 healthy/success。

## 上下文压缩可见性

- patcher 从 Hermes `_status_callback_sync` 的精确 `Compacting context` 状态标记生成 `context-compaction` notice，不用普通 compression 文本、静默 watchdog 或虚构百分比推断。
- 已有 primary card 会在 Header 显示“正在压缩上下文”；没有现有卡时创建且只创建一张 primary card，并保持私聊/topic reply anchor。
- 后续 answer/tool/terminal 事件会清除压缩阶段并继续更新同一张卡；doctor/capability 诊断明确显示 `status_callback` 是否可用。
- 不兼容或缺少 callback 的 Hermes 版本保持 fail-open，不影响其他卡片路径。

## 可配置文本字号

- `card.text_sizes` 支持 `body`、`reasoning`、`tool`、`notice`、`footer` 五个角色。
- 每个角色可以使用一个 Feishu CardKit 字号，也可以配置 `default` / `pc` / `mobile` 映射；base/profile/bot 层只对该字段做受控 deep merge。
- schema 只接受已知角色、设备字段和 CardKit 字号；错误会带精确配置路径，不输出配置或凭据。
- 未配置时 Card JSON 保持原默认结构。卡片物理 width/height 由 Feishu/Lark 客户端控制，本版本不承诺像素尺寸。

```yaml
card:
  text_sizes:
    body: normal
    footer:
      default: x-small
      pc: x-small
      mobile: notation
```

## selected env 与 Noop 可观测性

- `setup` / `start --env-file ...` 选中的 env file 现在同时用于 runner 和运维诊断加载飞书凭据；优先级为 YAML < 配置同目录 `.env` < selected env file < process environment。
- 不会无条件读取全局 `~/.hermes/.env`，避免跨 profile、容器或自定义 config 误取凭据；安装侧 `HFC_ENV_KEYS` 继续保持 secret-free。
- 缺凭据时 runner 输出不含路径和 secret 的明确 warning；`/health` 返回 `status: degraded`、`noop_mode: true`、`delivery.mode: noop`。
- Noop 发送返回 `not_sent`，增加 `feishu_noop_attempts` 和 `feishu_send_failures`，不再生成假 message id，也不增加 `feishu_send_successes`。
- 进程管理把 degraded sidecar 视为“正在运行但不可投递”，因此 `start/status/stop` 仍可管理和修复它。

## 验证边界

- 自动化覆盖 compaction patch/install、status 分类、session/render/server 生命周期、topic/sequence race、capability/doctor，以及 text-size schema、merge、角色渲染和 PC/mobile alias。
- 最终全量自动化为 `1460 passed, 4 skipped`，并通过 `git diff --check`。
- `uv build` 成功生成 sdist/wheel；干净 Python 3.12 环境从 wheel 导入 `hermes_feishu_card==4.0.12`，distribution version 与 console entry point metadata 正确。
- selected-env 真实子进程启动验证为 `healthy/live`；无凭据子进程验证为 `degraded/noop`，投递返回 `not_sent` 且 success 保持为 0。
- 候选 runtime 已通过官方 setup/patcher 装入真实 Hermes，doctor 确认 `status_callback` capability 与 install state 一致；字号演示卡完成 create + update。
- 手动 `/compress` 不经过 `_status_callback_sync`，因此不作为自动压缩 callback 证据。按发布决定未执行自动压缩长会话 smoke，也不宣称桌面/移动端最终视觉验收或报告者 Linux/systemd 复验已完成。

## Release assets

- `hermes-feishu-card-v4.0.12-macos.tar.gz`
- `hermes-feishu-card-v4.0.12-linux.tar.gz`
- `hermes-feishu-card-v4.0.12-windows.zip`
- `hermes-feishu-card-v4.0.12-checksums.txt`

发布后验证：annotated tag `v4.0.12` 指向合并提交 `00a48a7`；release-assets workflow `29632908140` 成功。下载四个公开资产后，Linux、macOS、Windows 包的 SHA-256 校验全部通过；隔离 Python 3.12 环境从公开 tag 安装并从 `site-packages` 导入 `4.0.12`，CLI smoke 通过。Issues #133 和 #136 已附验证边界回复并关闭。

## Credits

- 感谢 @tianxia3111 提交 Issue #133 的生产压缩空窗与移动端可读性需求。
- 感谢 @Jasonsun77 进一步确认自定义字号需求。
- 感谢 @nasvip 在 Issue #136 提供完整 Linux/systemd 凭据传播链、health/metrics 证据与根因定位。
