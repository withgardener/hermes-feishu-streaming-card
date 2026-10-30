# V3.8.6 Release Notes

V3.8.6 is a Docker/install compatibility patch for issue #70.

## What Changed

- Docker and source-stripped Hermes installs no longer fail only because `HERMES_DIR/VERSION` is absent.
- If `VERSION` is missing and the Hermes root is not a standalone git checkout, the installer reads `gateway/run.py` and uses verified patch anchors to decide support.
- `doctor --explain` now reports `version_source: gateway anchors`, `version: unknown`, and the inferred hook strategy when this fallback is used.
- Hermes v0.18.0 / `v2026.7.1` is included in the compatibility matrix and continues to use `gateway_run_013_plus`.
- Explicit bad `VERSION` contents still fail closed; only missing metadata can fall back to anchors.
- README now uses a combined horizontal real-UI showcase image for command cards, command result feedback, and answer/tool timeline rendering.

## Docker Upgrade

Inside the existing Hermes container:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.6
bash install-docker.sh
```

If the container uses non-default paths, keep setting `HERMES_DIR`, `HFC_CONFIG`, `HFC_ENV_FILE`, or `HFC_PYTHON` as before.

## Verification

- `python -m pytest tests/unit/test_installer_detection.py tests/unit/test_install_scripts.py tests/unit/test_docs.py -q`
- Manual doctor smoke with a Hermes fixture whose `VERSION` file was removed:

```text
Hermes: supported (unknown, gateway_run_013_plus, compatibility partial)
```

## Release Assets

GitHub Releases include:

- `hermes-feishu-card-v3.8.6-macos.tar.gz`
- `hermes-feishu-card-v3.8.6-linux.tar.gz`
- `hermes-feishu-card-v3.8.6-windows.zip`
- `hermes-feishu-card-v3.8.6-checksums.txt`
