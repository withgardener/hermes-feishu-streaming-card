    def invoke_hook(self, hook_name: str, **kwargs: Any) -> List[Any]:
        """Call all registered callbacks for *hook_name*.

        Each callback is wrapped in its own try/except so a misbehaving
        plugin cannot break the core agent loop.

        Returns a list of non-``None`` return values from callbacks.

        For ``pre_llm_call``, callbacks may return a dict describing
        context to inject into the current turn's user message::

            {"context": "recalled text..."}
            "recalled text..."          # plain string, equivalent

        Context is ALWAYS injected into the user message, never the
        system prompt.  This preserves the prompt cache prefix — the
        system prompt stays identical across turns so cached tokens
        are reused.  All injected context is ephemeral — never
        persisted to session DB.
        """
        kwargs.setdefault("telemetry_schema_version", OBSERVER_SCHEMA_VERSION)
        callbacks = self._hooks.get(hook_name, [])
        results: List[Any] = []
        for cb in callbacks:
            try:
                ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as exc:
                logger.warning(
                    "Hook '%s' callback %s raised: %s",
                    hook_name,
                    getattr(cb, "__name__", repr(cb)),
                    exc,
                )
        return results
