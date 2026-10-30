    def _discover_and_load_inner(self) -> None:
        """The actual discovery sweep — see :meth:`discover_and_load`."""
        manifests: List[PluginManifest] = []

        # 1. Bundled plugins (<repo>/plugins/<name>/)
        #
        # Repo-shipped plugins live next to hermes_cli/. Two layouts are
        # supported (see ``_scan_directory`` for details):
        #
        #   - flat: ``plugins/disk-cleanup/plugin.yaml`` (standalone)
        #   - category: ``plugins/image_gen/openai/plugin.yaml`` (backend)
        #
        # ``memory/``, ``context_engine/``, and ``model-providers/`` are
        # skipped at the top level — they have their own discovery systems
        # (plugins/memory/__init__.py, providers/__init__.py). ``platforms/``
        # is a category holding platform adapters (scanned one level deeper
        # below).
        repo_plugins = get_bundled_plugins_dir()
        logger.debug("Scanning bundled plugins: %s", repo_plugins)
        bundled = self._scan_directory(
            repo_plugins,
            source="bundled",
            skip_names={"memory", "context_engine", "platforms", "model-providers"},
        )
        logger.debug("  bundled (top-level): %d manifest(s)", len(bundled))
        manifests.extend(bundled)
        bundled_platforms = self._scan_directory(
            repo_plugins / "platforms", source="bundled"
        )
        logger.debug("  bundled/platforms: %d manifest(s)", len(bundled_platforms))
        manifests.extend(bundled_platforms)

        # 2. User plugins (~/.hermes/plugins/)
        user_dir = get_hermes_home() / "plugins"
        logger.debug("Scanning user plugins: %s", user_dir)
        user_manifests = self._scan_directory(user_dir, source="user")
        logger.debug("  user: %d manifest(s)", len(user_manifests))
        manifests.extend(user_manifests)

        # 3. Project plugins (./.hermes/plugins/)
        if _env_enabled("HERMES_ENABLE_PROJECT_PLUGINS"):
            project_dir = Path.cwd() / ".hermes" / "plugins"
            logger.debug("Scanning project plugins: %s", project_dir)
            project_manifests = self._scan_directory(project_dir, source="project")
            logger.debug("  project: %d manifest(s)", len(project_manifests))
            manifests.extend(project_manifests)
        else:
            logger.debug(
                "Project plugins disabled (set HERMES_ENABLE_PROJECT_PLUGINS=1 to enable)"
            )

        # 4. Pip / entry-point plugins
        ep_manifests = self._scan_entry_points()
        logger.debug("  entrypoints: %d manifest(s)", len(ep_manifests))
        manifests.extend(ep_manifests)

        # Load each manifest (skip user-disabled plugins).
        # Later sources override earlier ones on key collision — user
        # plugins take precedence over bundled, project plugins take
        # precedence over user. Dedup here so we only load the final
        # winner. Keys are path-derived (``image_gen/openai``,
        # ``disk-cleanup``) so ``tts/openai`` and ``image_gen/openai``
        # don't collide even when both manifests say ``name: openai``.
        disabled = _get_disabled_plugins()
        enabled = _get_enabled_plugins()  # None = opt-in default (nothing enabled)
        winners: Dict[str, PluginManifest] = {}
        for manifest in manifests:
            winners[manifest.key or manifest.name] = manifest
        for manifest in winners.values():
            lookup_key = manifest.key or manifest.name

            # Explicit disable always wins (matches on key or on legacy
            # bare name for back-compat with existing user configs).
            if lookup_key in disabled or manifest.name in disabled:
                loaded = LoadedPlugin(manifest=manifest, enabled=False)
                loaded.error = "disabled via config"
                self._plugins[lookup_key] = loaded
                logger.debug("Skipping disabled plugin '%s'", lookup_key)
                continue

            # Exclusive plugins (memory providers) have their own
            # discovery/activation path. The general loader records the
            # manifest for introspection but does not load the module.
            if manifest.kind == "exclusive":
                loaded = LoadedPlugin(manifest=manifest, enabled=False)
                loaded.error = (
                    "exclusive plugin — activate via <category>.provider config"
                )
                self._plugins[lookup_key] = loaded
                logger.debug(
                    "Skipping '%s' (exclusive, handled by category discovery)",
                    lookup_key,
                )
                continue

            # Model provider plugins are loaded by providers/__init__.py
            # (its own lazy discovery keyed off first get_provider_profile()
            # call). We record the manifest here for introspection but do
            # not import the module — a second import would create two
            # ProviderProfile instances and break the "last writer wins"
            # override semantics between bundled and user plugins.
            if manifest.kind == "model-provider":
                loaded = LoadedPlugin(manifest=manifest, enabled=True)
                self._plugins[lookup_key] = loaded
                logger.debug(
                    "Skipping '%s' (model-provider, handled by providers/ discovery)",
                    lookup_key,
                )
                continue

            # Built-in backends auto-load — they ship with hermes and must
            # just work. Selection among them (e.g. which image_gen backend
            # services calls) is driven by ``<category>.provider`` config,
            # enforced by the tool wrapper.
            if manifest.source == "bundled" and manifest.kind == "backend":
                self._load_plugin(manifest)
                continue

            # Bundled platform plugins (gateway adapters: telegram, discord,
            # feishu, teams, ...) are registered LAZILY. Their modules import
            # heavy, platform-specific SDKs at module level (lark_oapi,
            # microsoft_teams, discord.py, slack_bolt, ...), so eagerly loading
            # all ~20 of them added several seconds to every `hermes`
            # invocation — including plain `hermes chat`, which never touches a
            # gateway platform. Instead we register a cheap deferred loader in
            # the platform_registry keyed on the platform name; the real module
            # is imported only when the gateway / cron / setup / send_message
            # path actually asks for that platform. Every platform Hermes ships
            # remains available out of the box — it just loads on first use.
            if manifest.source == "bundled" and manifest.kind == "platform":
                self._register_deferred_platform(manifest)
                continue

            # Everything else (standalone, user-installed backends,
            # entry-point plugins) is opt-in via plugins.enabled.
            # Accept both the path-derived key and the legacy bare name
            # so existing configs keep working.
            is_enabled = (
                enabled is not None
                and (lookup_key in enabled or manifest.name in enabled)
            )
            if not is_enabled:
                loaded = LoadedPlugin(manifest=manifest, enabled=False)
                loaded.error = (
                    "not enabled in config (run `hermes plugins enable {}` to activate)"
                    .format(lookup_key)
                )
                self._plugins[lookup_key] = loaded
                logger.debug(
                    "Skipping '%s' (not in plugins.enabled)", lookup_key
                )
                continue
            self._load_plugin(manifest)

        if manifests:
            logger.info(
                "Plugin discovery complete: %d found, %d enabled",
                len(self._plugins),
                sum(1 for p in self._plugins.values() if p.enabled),
            )
