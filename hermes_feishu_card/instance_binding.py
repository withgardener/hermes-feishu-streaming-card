"""Bind a source checkout to one process HOME, without ambient HOME inference."""
from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any, Mapping


def configured_hermes_home(root: Path, config: Mapping[str, Any]) -> Path:
    """An explicit sidecar setting is authoritative; legacy layouts stay unchanged."""
    selected_root = Path(root).expanduser().resolve()
    value = (config.get('service') or {}).get('hermes_home')
    if value is None:
        return selected_root.parent
    if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
        raise ValueError('service.hermes_home must be an absolute Hermes HOME')
    try:
        home = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('service.hermes_home is unavailable') from exc
    if not home.is_dir():
        raise ValueError('service.hermes_home must be a directory')
    # Legacy source-parent installations can bootstrap before Hermes setup.
    # A split HOME needs its config to establish the explicit instance binding.
    if home != selected_root.parent and not (home / 'config.yaml').is_file():
        raise ValueError('service.hermes_home requires a Hermes config.yaml')
    return home


def gateway_process_binding() -> tuple[Path, Path] | None:
    """Read Hermes' process-scoped API, never a callback/profile/environment claim."""
    source = getattr(sys.modules.get('gateway.run'), '__file__', None)
    if not isinstance(source, str) or not source:
        return None
    try:
        source = Path(source).resolve(strict=True)
        if source.parent.name != 'gateway' or not source.is_file():
            return None
        root = source.parent.parent
        constants = importlib.import_module('hermes_constants')
        resolver = getattr(constants, 'get_process_hermes_home', None)
        process_scoped = callable(resolver)
        if not process_scoped:
            resolver = getattr(constants, 'get_hermes_home', None)
        if not callable(resolver):
            return None
        value = Path(resolver()).expanduser()
        if not value.is_absolute():
            return None
        home = value.resolve(strict=True)
        if not home.is_dir():
            return None
        if home != root.parent:
            # Old profile-local APIs cannot prove the process drain directory.
            if not process_scoped or not (home / 'config.yaml').is_file():
                return None
        return root, home
    except Exception:
        return None


def setup_hermes_home(root: Path, config: Mapping[str, Any], requested: str | Path | None) -> Path | None:
    existing = (config.get('service') or {}).get('hermes_home')
    if requested is None:
        return configured_hermes_home(root, config) if existing is not None else None
    selected = configured_hermes_home(root, {'service': {'hermes_home': str(Path(requested).expanduser())}})
    if existing is not None and configured_hermes_home(root, config) != selected:
        raise ValueError('--hermes-home conflicts with the configured sidecar HOME')
    return selected
