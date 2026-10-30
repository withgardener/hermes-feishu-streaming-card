        parent_session_id = getattr(parent_agent, "session_id", None)
        try:
            from hermes_cli.plugins import invoke_hook as invoke_hook
        except Exception:
            invoke_hook = None

        children_cost_total = 0.0
        for entry in results:
            child_role = entry.pop("_child_role", None)
            child_cost = entry.pop("_child_cost_usd", 0.0)
            try:
                if child_cost:
                    children_cost_total += float(child_cost)
            except (TypeError, ValueError):
                pass
            if invoke_hook is None:
                continue
            try:
                child_index = entry.get("task_index", -1)
                child = child_by_index.get(child_index)
                invoke_hook(
                    "subagent_stop",
                    parent_session_id=parent_session_id,
                    parent_turn_id=getattr(parent_agent, "_current_turn_id", "") or "",
                    child_session_id=getattr(child, "session_id", None),
                    child_role=child_role,
                    child_summary=entry.get("summary"),
                    child_status=entry.get("status"),
                    tool_call_history=_subagent_stop_tool_call_history(
                        entry.get("tool_trace")
                    ),
                    duration_ms=int((entry.get("duration_seconds") or 0) * 1000),
                )
            except Exception:
                logger.debug("subagent_stop hook invocation failed", exc_info=True)
