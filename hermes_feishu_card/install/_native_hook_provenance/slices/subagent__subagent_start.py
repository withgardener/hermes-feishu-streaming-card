    # Stash the post-degrade role for introspection (leaf if the
    # kill switch or depth bounded the caller's requested role).
    child._delegate_role = effective_role
    # Stash subagent identity for nested-delegation event propagation and
    # for _run_single_child / interrupt_subagent to look up by id.
    child._subagent_id = subagent_id
    child._parent_subagent_id = parent_subagent_id
    child._subagent_goal = goal
    child._parent_turn_id = getattr(parent_agent, "_current_turn_id", "") or ""
    # Stable sidebar marker: delegate subagent sessions must stay out of
    # session pickers even when a parent delete orphans them (parent_session_id
    # → NULL). Mirrors /branch's ``_branched_from`` pattern — see
    # ``list_sessions_rich`` child-exclusion clause.
    parent_sid = getattr(parent_agent, "session_id", None)
    if parent_sid and getattr(child, "_session_init_model_config", None) is not None:
        child._session_init_model_config["_delegate_from"] = parent_sid

    # Share a credential pool with the child when possible so subagents can
    # rotate credentials on rate limits instead of getting pinned to one key.
    child_pool = _resolve_child_credential_pool(
        effective_provider, parent_agent, effective_base_url
    )
    if child_pool is not None:
        child._credential_pool = child_pool

    # Register child for interrupt propagation
    if hasattr(parent_agent, "_active_children"):
        lock = getattr(parent_agent, "_active_children_lock", None)
        if lock:
            with lock:
                parent_agent._active_children.append(child)
        else:
            parent_agent._active_children.append(child)

    # Announce the spawn immediately — the child may sit in a queue
    # for seconds if max_concurrent_children is saturated, so the TUI
    # wants a node in the tree before run starts.
    if child_progress_cb:
        try:
            child_progress_cb("subagent.spawn_requested", preview=goal)
        except Exception as exc:
            logger.debug("spawn_requested relay failed: %s", exc)

    try:
        from hermes_cli.lifecycle import invoke_hook as _invoke_hook
        _invoke_hook(
            "subagent_start",
            parent_session_id=getattr(parent_agent, "session_id", None),
            parent_turn_id=getattr(parent_agent, "_current_turn_id", "") or "",
            parent_subagent_id=parent_subagent_id,
            child_session_id=getattr(child, "session_id", None),
            child_subagent_id=subagent_id,
            child_role=effective_role,
            child_goal=goal,
        )
    except Exception:
        logger.debug("subagent_start hook invocation failed", exc_info=True)

    return child
