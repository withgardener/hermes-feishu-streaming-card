# V3.8.13 Release Notes

V3.8.13 is a compatibility hotfix for Hermes upgrades, especially Hermes `v2026.7.7.2` / `0.18.2`, where cards could stop working after the upstream Gateway replaced `gateway/run.py`.

## What Changed

- **Hermes version parsing is more tolerant**: four-component tags such as `v2026.7.7.2`, semantic versions such as `0.18.2`, and descriptive strings such as `Hermes Agent v0.18.2 (...)` are recognized.
- **Gateway anchors are the final compatibility gate**: if readable version metadata is unparseable but `gateway/run.py` still exposes safe hook anchors, `doctor`, `install`, and `setup` can continue with `VERSION + gateway anchors` or `git tag + gateway anchors`.
- **Hermes upgrade stale state is repairable**: when an upstream Hermes upgrade leaves `run.py` unpatched but old HFC backup/manifest files behind, `repair` clears the stale install state and `install` can patch the upgraded Gateway again.

## Upgrade

```bash
export HFC_VERSION=v3.8.13
bash install.sh
```

Docker/container installs:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v3.8.13
bash install-docker.sh
```

After upgrading Hermes itself, rerun HFC setup or install so the hook is refreshed against the new `gateway/run.py`:

```bash
python3 -m hermes_feishu_card.cli repair --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
hermes gateway restart
```

Expected `doctor --explain` result after repair/install:

```text
Hermes: supported (v2026.7.7.2, gateway_run_013_plus, compatibility full)
Install state: installed - Hermes Feishu hook install state is complete and consistent.
```

## Artifacts

GitHub Release assets are expected after publishing:

- `hermes-feishu-card-v3.8.13-macos.tar.gz`
- `hermes-feishu-card-v3.8.13-linux.tar.gz`
- `hermes-feishu-card-v3.8.13-windows.zip`
- `hermes-feishu-card-v3.8.13-checksums.txt`

## Verification

- Full pytest suite: `736 passed`.
- `git diff --check`.
- Local Hermes `v2026.7.7.2` doctor/install/restart smoke: `gateway_run_013_plus`, runtime import ok, install state complete and consistent.
