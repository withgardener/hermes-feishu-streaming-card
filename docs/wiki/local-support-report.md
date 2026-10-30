# 本地诊断报告（开发分支）

排查问题时，先预览可分享的诊断字段：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --support-report
```

需要保存时指定一个尚不存在的文件：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --export-report ./hfc-support.json
```

这两个命令执行原有只读诊断；导出命令先把相同结构的报告输出到终端，再写入新文件。它们不修复、重启或上传，不创建 issue，也不发送聊天消息。诊断结果仍沿用 doctor 退出码：命令成功生成报告并不代表诊断发现全部健康。

报告包含 HFC/Python/平台版本、现有诊断白名单中的状态、受控原因及[事件耗时统计](observed-timing.md)，并提供内容摘要 `report_id` 供人工对应。配置原文、日志、聊天记录、凭据、本机路径和服务地址不进入报告。它不是完整日志采集包。

导出上限为 128 KiB；超过限制拒绝写入，不默默删掉故障信息。目标已存在（包括符号链接）时拒绝覆盖。POSIX 创建权限为 `0600`；写入异常可能留下仅供本机检查的部分文件，程序不会为了清理而删除一个可能已被其他进程替换的路径。再次导出应使用新文件名。

普通 `doctor --json`、`--explain` 保持已有输出；它们与报告选项互斥。分享前仍可自行检查生成的文件内容。运行时和安装器的真实故障复现，需要另附明确授权且脱敏的证据。
