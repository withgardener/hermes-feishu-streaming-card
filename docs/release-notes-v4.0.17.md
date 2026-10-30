# V4.0.17

V4.0.17 修复 V4.0.16 在并行同名工具调用中的事件串线：每次调用使用 Hermes 的真实 `call_id` 独立关联，工具次数、查询详情和耗时重新保持一致。

## 修复内容

- patcher 包装 Hermes `tool_start_callback` 与 `tool_complete_callback`，使用稳定调用 ID 配对 started/completed 事件。
- 两个并行 `web_search` 即使工具名相同，也分别保留自己的查询摘要、参数、状态和耗时，不再把第二条查询重复显示在两行。
- “思考与工具”中的次数按真实 invocation 计数；一次工具的 started/completed 只计为一次。
- renderer 会移除工具详情中的全部 `耗时:` 元数据行，只把第一个有效耗时放在紧凑标题中，避免第二个耗时残留在详情末尾。

## 兼容性与安全边界

- 已有 Hermes start/complete callback 会被安全包装并继续调用；缓存 agent 不会继承上一轮 HFC callback 闭包。
- 只有 patcher 验证到兼容的 callback assignment 和运行时作用域时才启用稳定 ID 路径。
- 缺少稳定 callback 锚点的旧 Hermes 继续使用原有 progress callback fallback，不扩大 patch 范围，也不直接修改 Hermes 其他文件。

## 验证

- 真实问题序列回归：两个同名 `web_search` 先 started、再分别 completed，最终得到两条独立详情、`2 次工具调用` 和各自的 `2.12s` / `2.47s`。
- 本机当前 Hermes 原始 `gateway/run.py` 备份验证：patch 插入后可编译、重复安装幂等、`remove_patch` 精确还原。
- 完整自动化通过：`1508 passed, 4 skipped`；`git diff --check` 通过。
- sdist/wheel、隔离 `site-packages` 导入、公开 tagged installer、Release assets 与本机运行来源在发布流程中复核。

## Release assets

- `hermes-feishu-card-v4.0.17-macos.tar.gz`
- `hermes-feishu-card-v4.0.17-linux.tar.gz`
- `hermes-feishu-card-v4.0.17-windows.zip`
- `hermes-feishu-card-v4.0.17-checksums.txt`
