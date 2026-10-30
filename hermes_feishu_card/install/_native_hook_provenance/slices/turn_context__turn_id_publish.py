    agent._persist_user_message_idx = None
    agent._persist_user_message_override = persist_user_message
    agent._persist_user_message_timestamp = persist_user_timestamp
    # Generate unique task_id if not provided to isolate VMs between tasks.
    effective_task_id = task_id or str(uuid.uuid4())
    agent._current_task_id = effective_task_id
    turn_id = str(getattr(agent, "_relay_pending_turn_id", "") or "")
    if not turn_id:
        turn_id = (
            f"{agent.session_id or 'session'}:{effective_task_id}:{uuid.uuid4().hex[:8]}"
        )
    agent._relay_pending_turn_id = None
    agent._current_turn_id = turn_id
    agent._current_api_request_id = ""
    # Tripwire: warn (with both turn ids) when this turn starts before the
