    def _load_plugin(self, manifest: PluginManifest) -> None:
        """Import a plugin module and call its ``register(ctx)`` function."""
        loaded = LoadedPlugin(manifest=manifest)
        logger.debug(
            "Loading plugin '%s' (source=%s, kind=%s, path=%s)",
            manifest.key or manifest.name, manifest.source, manifest.kind, manifest.path,
        )

        from tools.registry import registry as _registry
        _plugin_id = manifest.key or manifest.name
        _slug = _plugin_id.replace("/", "__").replace("-", "_")
        _registry.register_plugin_override_policy(
            f"{_NS_PARENT}.{_slug}",
            PluginContext(manifest, self)._tool_override_allowed(""),
        )
        try:
            if manifest.source in {"user", "project", "bundled"}:
                module = self._load_directory_module(manifest)
            else:
                module = self._load_entrypoint_module(manifest)

            loaded.module = module

            # Call register()
            register_fn = getattr(module, "register", None)
            if register_fn is None:
                loaded.error = "no register() function"
                logger.warning("Plugin '%s' has no register() function", manifest.name)
            else:
                ctx = PluginContext(manifest, self)
                # Snapshot registry state BEFORE register() so each registry's
                # attribution counts only what THIS plugin actually added.
                # The previous approach diffed names against all already-loaded
                # plugins, which mis-credited a plugin that registered a hook /
                # middleware / tool name an earlier plugin had already used:
                # the shared name was attributed to the first plugin only, so
                # later plugins under-reported in `hermes plugins list`.
                _tools_before = set(self._plugin_tool_names)
                _hook_counts_before = {
                    h: len(cbs) for h, cbs in self._hooks.items()
                }
                _mw_counts_before = {
                    kind: len(cbs) for kind, cbs in self._middleware.items()
                }
                register_fn(ctx)
                loaded.tools_registered = [
                    t for t in self._plugin_tool_names
                    if t not in _tools_before
                ]
                loaded.hooks_registered = [
                    h
                    for h, cbs in self._hooks.items()
                    if len(cbs) > _hook_counts_before.get(h, 0)
                ]
                loaded.middleware_registered = [
                    kind
                    for kind, cbs in self._middleware.items()
                    if len(cbs) > _mw_counts_before.get(kind, 0)
                ]
                loaded.commands_registered = [
                    c for c in self._plugin_commands
                    if self._plugin_commands[c].get("plugin") == manifest.name
                ]
                loaded.enabled = True
                logger.debug(
                    "  registered: %d tool(s), %d hook(s), %d middleware, %d slash command(s), %d CLI command(s)",
                    len(loaded.tools_registered),
                    len(loaded.hooks_registered),
                    len(loaded.middleware_registered),
                    len(loaded.commands_registered),
                    sum(
                        1 for c in self._cli_commands
                        if self._cli_commands[c].get("plugin") == manifest.name
                    ),
                )

        except Exception as exc:
            loaded.error = str(exc)
            logger.warning(
                "Failed to load plugin '%s': %s",
                manifest.name, exc, exc_info=_PLUGINS_DEBUG,
            )
        self._plugins[manifest.key or manifest.name] = loaded
