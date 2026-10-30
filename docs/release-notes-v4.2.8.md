# Hermes Feishu Streaming Card V4.2.8

发布日期：2026-08-05

V4.2.8 修复公开 v4.2.7 安装验收发现的凭据持久化缺口。

## 修复内容

- `install.sh` 会把通过进程环境传入的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 写入指定的私有 `.env`，不再只在安装进程内临时可见。
- `install-docker.sh` 使用同一持久化契约，适配非交互容器安装和 Compose setup。
- `install.ps1` 在 Windows 上同样持久化进程凭据，并规范化替换既有 dotenv assignment。
- POSIX 安装器将凭据文件权限收紧为 `0600`；三个安装器都不会把凭据内容写入日志。

## 验证范围

- 新增 macOS/Linux installer、Docker installer 和 PowerShell installer 回归，覆盖进程凭据、带空格 secret、dotenv 写入和日志不泄露。
- 完整 release gate 仍包含 Python 3.9/3.12、Windows PowerShell、Docker Compose、Feishu SDK、精确 main merge SHA、公开 tag 安装与 Release assets checksum。

## 安装

macOS / Linux：

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v4.2.8
bash install.sh
```

Windows PowerShell：

```powershell
$env:FEISHU_APP_ID = "cli_xxx"
$env:FEISHU_APP_SECRET = "xxx"
$env:HFC_VERSION = "v4.2.8"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.8/install.ps1" | iex
```

安装后运行：

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card status --config /path/to/config.yaml
```

包内 Python import 应来自目标环境的 `site-packages`，package/distribution 版本均为 `4.2.8`。

## Release assets

- `hermes-feishu-card-v4.2.8-macos.tar.gz`
- `hermes-feishu-card-v4.2.8-linux.tar.gz`
- `hermes-feishu-card-v4.2.8-windows.zip`
- `hermes-feishu-card-v4.2.8-checksums.txt`

下载后请按 checksums 文件核对 SHA-256。
