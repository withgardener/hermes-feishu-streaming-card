from __future__ import annotations

from collections.abc import Callable, Iterable


class PluginContext:
    def __init__(self, reject_hooks: Iterable[str] = ()):
        self._reject_hooks = frozenset(reject_hooks)
        self.registered: dict[str, Callable] = {}

    def register_hook(self, name: str, callback: Callable) -> None:
        if name in self._reject_hooks:
            raise ValueError(f"fixture host rejected hook: {name}")
        self.registered[name] = callback
