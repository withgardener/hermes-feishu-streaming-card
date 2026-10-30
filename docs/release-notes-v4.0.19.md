# V4.0.19 发布说明

发布日期：2026-07-22

V4.0.19 是 one-line installer 热修。它修复了 Hermes venv 已被正确识别、但安装命令仍错误附带 `pip --user` 的问题，并确保 pip 失败时不会继续调用旧版本的 setup。

## 修复

- `install.sh` 选中 `HERMES_DIR/venv`、`.venv` 或 Gateway venv 中的 Python 时，默认使用普通 venv install，不再添加 `--user`。
- 回退到 system Python 时仍默认使用 user install；显式 `HFC_PIP_USER` 继续优先。
- pip 首次安装或 `--break-system-packages` 重试失败时保留真实退出码、输出真实错误并立即停止，不再产生“显示升级完成但实际仍运行旧版本”的假成功。

## 验证

- installer 聚焦回归：`22 passed, 3 skipped`。
- 全量自动化：`1513 passed, 4 skipped`。
- fresh Hermes venv 未设置 `HFC_PIP_USER`，真实安装完成后从 venv `site-packages` 导入目标版本。
- 发布资产：
  - `hermes-feishu-card-v4.0.19-macos.tar.gz`
  - `hermes-feishu-card-v4.0.19-linux.tar.gz`
  - `hermes-feishu-card-v4.0.19-windows.zip`
  - `hermes-feishu-card-v4.0.19-checksums.txt`

## 升级

```bash
export HFC_VERSION=v4.0.19
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```
