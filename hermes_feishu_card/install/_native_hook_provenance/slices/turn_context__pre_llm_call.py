    # Plugin hook: pre_llm_call (context injected into user message, not system prompt).
    plugin_user_context = ""
    try:
        from hermes_cli.lifecycle import invoke_hook as _invoke_hook
        _pre_results = _invoke_hook(
            "pre_llm_call",
            session_id=agent.session_id,
            task_id=effective_task_id,
            turn_id=turn_id,
            user_message=original_user_message,
            conversation_history=list(messages),
            is_first_turn=(not bool(conversation_history)),
            model=agent.model,
            platform=getattr(agent, "platform", None) or "",
            parent_session_id=getattr(agent, "_parent_session_id", None) or "",
            sender_id=getattr(agent, "_user_id", None) or "",
        )
        _ctx_parts: list[str] = []
        # Spill oversized per-hook context to disk so a runaway plugin
        # can't inflate every subsequent turn's prompt. Ported from
        # openai/codex PR #21069 ("Spill large hook outputs from context").
        try:
            from tools.hook_output_spill import (
                get_spill_config as _spill_cfg,
                spill_if_oversized as _spill_if_oversized,
            )
            _spill_config_cached = _spill_cfg()
        except Exception:
            _spill_if_oversized = None  # type: ignore[assignment]
            _spill_config_cached = None
        for r in _pre_results:
            _piece: str = ""
            if isinstance(r, dict) and r.get("context"):
                _piece = str(r["context"])
            elif isinstance(r, str) and r.strip():
                _piece = r
            else:
                continue
            if _spill_if_oversized is not None:
                try:
                    _piece = _spill_if_oversized(
                        _piece,
                        session_id=agent.session_id,
                        source="plugin hook",
                        config=_spill_config_cached,
                    )
                except Exception as _spill_exc:
                    logger.warning("hook context spill failed: %s", _spill_exc)
            _ctx_parts.append(_piece)
        if _ctx_parts:
            plugin_user_context = "\n\n".join(_ctx_parts)
    except Exception as exc:
        logger.warning("pre_llm_call hook failed: %s", exc)
