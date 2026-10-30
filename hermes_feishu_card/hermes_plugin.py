from __future__ import annotations

import importlib
from typing import Any


def register(ctx: Any) -> None:
    try:
        runtime = importlib.import_module(
            ".hermes_plugin_runtime", package=__package__
        )
        runtime.bootstrap_plugin_runtime(ctx)
    except Exception:
        return None
    return None
