        # Internal events (e.g. background-process completion notifications)
        # are system-generated and must skip user authorization.
        is_internal = bool(getattr(event, "internal", False))

        # Ignored-channel guard runs FIRST — before startup-restore queueing,
        # plugin hooks, auth, and session setup — so a configured ignored
        # channel can never reach pairing/auth/session state (#51899).
        # getattr: bare test runners construct GatewayRunner via
        # object.__new__ without config (see AGENTS.md pitfall on
        # object.__new__ test pattern).
        if (
            not is_internal
            and getattr(source, "platform", None) == Platform.SLACK
            and _is_slack_ignored_channel(
                getattr(self, "config", None), getattr(source, "chat_id", None)
            )
        ):
            logger.info(
                "Dropping Slack message from configured ignored channel %s",
                getattr(source, "chat_id", None),
            )
            return None

        if (
            getattr(self, "_startup_restore_in_progress", False)
            and not is_internal
            and not getattr(event, "_hermes_startup_restore_replay", False)
        ):
            self._queue_startup_restore_event(event)
            return None

        # scale-to-zero (Phase 0, 0.B/F13): stamp the gateway-scoped last-inbound
        # clock for real (user-originated) inbound only. Internal/system events
        # (background-process completions, startup-restore replays) are NOT
        # traffic — counting them would keep a genuinely idle gateway awake. This
        # clock is what the idle predicate (gateway/scale_to_zero.is_idle) reads.
        if not is_internal:
            self._scale_to_zero_note_real_inbound()

        # Fire pre_gateway_dispatch plugin hook for user-originated messages.
        # Plugins receive the MessageEvent and may return a dict influencing flow:
        #   {"action": "skip",    "reason": ...}    -> drop (no reply, plugin handled)
        #   {"action": "rewrite", "text":  ...}     -> replace event.text, continue
        #   {"action": "allow"}   /   None          -> normal dispatch
        # Hook runs BEFORE auth so plugins can handle unauthorized senders
        # (e.g. customer handover ingest) without triggering the pairing flow.
        if not is_internal:
            try:
                from hermes_cli.lifecycle import invoke_hook as _invoke_hook
                _hook_results = _invoke_hook(
                    "pre_gateway_dispatch",
                    event=event,
                    gateway=self,
                    # getattr: bare-runner tests build GatewayRunner via
                    # object.__new__ without __init__ (pitfall #17), and the
                    # hook must not fail dispatch over a missing attribute.
                    session_store=getattr(self, "session_store", None),
                )
            except Exception as _hook_exc:
                logger.warning("pre_gateway_dispatch invocation failed: %s", _hook_exc)
                _hook_results = []

            for _result in _hook_results:
                if not isinstance(_result, dict):
                    continue
                _action = _result.get("action")
                if _action == "skip":
                    logger.info(
                        "pre_gateway_dispatch skip: reason=%s platform=%s chat=%s",
                        _result.get("reason"),
                        source.platform.value if source.platform else "unknown",
                        source.chat_id or "unknown",
                    )
                    return None
                if _action == "rewrite":
                    _new_text = _result.get("text")
                    if isinstance(_new_text, str):
                        event = dataclasses.replace(event, text=_new_text)
                        source = event.source
                    break
                if _action == "allow":
                    break

        if is_internal:
            pass
        elif source.user_id is None:
            # Messages with no user identity (Telegram service messages,
            # channel forwards, anonymous admin posts, sender_chat) can't
            # be paired, but they can still be authorized via a
            # chat-scoped allowlist (e.g. TELEGRAM_GROUP_ALLOWED_CHATS
            # authorizes every member of the listed chat regardless of
            # sender). Defer to _is_user_authorized so that path runs.
            if not self._is_user_authorized(source):
                logger.debug("Ignoring message with no user_id from %s", source.platform.value)
                return None
        elif not self._is_user_authorized(source):
            logger.warning("Unauthorized user: %s (%s) on %s", source.user_id, source.user_name, source.platform.value)
            # In DMs: offer pairing code. In groups: silently ignore.
