# V3.8.0 版本说明

V3.8.0 聚焦飞书卡片可读性、流式终态稳定性和真实部署诊断。核心目标是让飞书里的卡片更像一个可持续阅读的 Agent 工作台：最终答案保持在主内容区，思考和工具过程进入辅助 timeline，完成态不再被旧的中间更新覆盖。

## 核心改动

- 将主回答与 reasoning / tool timeline 分离展示，默认让最终答案留在最显眼的位置。
- 启用辅助 timeline 时隐藏底部重复的“工具调用 N 次”摘要，避免同一份工具信息出现两次。
- 合并 burst 场景下的卡片更新，并在 terminal card 渲染前 drain pending updates。
- 长 Markdown 表格和 fenced code block 跨卡片分块时保持结构，减少 raw Markdown 和半截 code fence。
- 新增卡片更新 metrics，覆盖 queue、coalescing、drain、Feishu update latency。
- `doctor` 的 Hermes runtime import 检查改为在 Hermes 项目根目录执行，避免当前开发仓库路径让 import 检查误判通过。

## 展示效果

README 首屏新增 V3.8.0 卡片截图：

- `docs/assets/feishu-v38-card-timeline.png`

该截图展示主回答区、表格内容、辅助 timeline 和工具状态折叠后的卡片结构。

## 安装与升级

现有用户不需要修改配置。升级后建议重新运行 `setup` 或 `install`，确保 Hermes runtime Python、hook 和 sidecar 版本一致：

```bash
git checkout v3.8.0
pip install -e ".[test]" --upgrade
python3 -m hermes_feishu_card.cli doctor --config ~/.hermes_feishu_card/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
```

如果使用一行安装脚本，可指定：

```bash
export HFC_VERSION=v3.8.0
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```

## Docker

Docker 仍然面向“已有 Hermes 容器内安装/更新”，本项目不发布官方 Hermes 镜像。V3.8.0 同步更新了：

- `docker-compose.example.yml`：默认 `HFC_VERSION=${HFC_VERSION:-v3.8.0}`。
- `README.md` / `README.en.md` / `README-install.md`：Docker 示例版本改为 `v3.8.0`。

容器内示例：

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.0
bash install-docker.sh
```

## 发布文件

GitHub Releases 包含：

- `hermes-feishu-card-v3.8.0-macos.tar.gz`
- `hermes-feishu-card-v3.8.0-linux.tar.gz`
- `hermes-feishu-card-v3.8.0-windows.zip`
- `hermes-feishu-card-v3.8.0-checksums.txt`

## 验证命令

- `.venv/bin/python -m pytest tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_text.py tests/unit/test_config.py -q`
- `.venv/bin/python -m pytest tests/integration/test_server.py -q`
- `.venv/bin/python -m pytest -q`
