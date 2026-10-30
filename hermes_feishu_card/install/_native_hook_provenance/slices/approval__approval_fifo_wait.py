def _await_gateway_decision(session_key: str, notify_cb, approval_data: dict,
                            *, surface: str = "gateway") -> dict:
    """Enqueue *approval_data*, notify the user, and block the calling agent
    thread until the request is resolved or the gateway approval timeout
    elapses — firing pre/post approval hooks and cleaning up the queue entry.

    Shared by the terminal command guard (``check_all_command_guards``) and
    the execute_code guard (``check_execute_code_guard``) so the fiddly
    heartbeat-polling wait loop lives in one place.

    Returns ``{"resolved": bool, "choice": str|None}`` on completion, or
    ``{"resolved": False, "choice": None, "notify_failed": True}`` if the
    notify callback raised.  Persistence of an approved choice and building
    the final tool-facing result dict remain the caller's responsibility.
    """
    command = approval_data.get("command", "")
    description = approval_data.get("description", "")
    primary_key = approval_data.get("pattern_key", "")
    all_keys = approval_data.get("pattern_keys", [primary_key])

    entry = _ApprovalEntry(approval_data)
    with _lock:
        _gateway_queues.setdefault(session_key, []).append(entry)

    def _drop_entry() -> None:
        with _lock:
            queue = _gateway_queues.get(session_key, [])
            if entry in queue:
                queue.remove(entry)
            if not queue:
                _gateway_queues.pop(session_key, None)

    # Notify plugins that an approval is being requested. Fires before the
    # gateway notify callback so observers get the event in real time.
    _fire_approval_hook(
        "pre_approval_request",
        command=command,
        description=description,
        pattern_key=primary_key,
        pattern_keys=list(all_keys),
        session_key=session_key,
        surface=surface,
    )

    # Notify the user (bridges sync agent thread → async gateway)
    try:
        notify_cb(approval_data)
    except Exception as exc:
        logger.warning("Gateway approval notify failed: %s", exc)
        _drop_entry()
        return {"resolved": False, "choice": None, "notify_failed": True}

    # Block until the user responds or the canonical approval timeout elapses
    # (default 300s). Poll in short slices so we can fire activity heartbeats
    # every ~10s to the agent's inactivity tracker — otherwise the gateway
    # watchdog kills the agent while the user is still responding. Mirrors
    # _wait_for_process() cadence.
    timeout = _get_approval_timeout()

    try:
        from tools.environments.base import touch_activity_if_due
    except Exception:  # pragma: no cover
        touch_activity_if_due = None

    _now = time.monotonic()
    _deadline = _now + max(timeout, 0)
    _activity_state = {"last_touch": _now, "start": _now}
    resolved = False
    while True:
        # Respect interrupt signals (e.g. /stop, /new, or an inactivity
        # timeout from the gateway) so a pending approval doesn't keep the
        # session wedged on threading.Event.wait() until the 5-minute approval
        # timeout. The wait runs on the agent's execution thread, which is the
        # exact thread AIAgent.interrupt() flags — so is_interrupted() here
        # sees the signal. Resolve as "deny" so the agent loop receives a
        # normal denial and unwinds cleanly (#8697).
        if is_interrupted():
            logger.info(
                "Approval wait interrupted by user signal — "
                "returning deny for session %s",
                session_key,
            )
            entry.result = "deny"
            entry.event.set()
            resolved = True
            break
        _remaining = _deadline - time.monotonic()
        if _remaining <= 0:
            break
        if entry.event.wait(timeout=min(1.0, _remaining)):
            resolved = True
            break
        if touch_activity_if_due is not None:
            touch_activity_if_due(_activity_state, "waiting for user approval")

    _drop_entry()

    choice = entry.result
    # Normalize outcome for the post hook. Unresolved (timeout) and None both
    # mean the user never responded; report that explicitly so plugins can
    # distinguish timeout from explicit deny.
    _outcome = "timeout" if not resolved else (choice if choice else "timeout")
    _fire_approval_hook(
        "post_approval_response",
        command=command,
        description=description,
        pattern_key=primary_key,
        pattern_keys=list(all_keys),
        session_key=session_key,
        surface=surface,
        choice=_outcome,
    )
    return {"resolved": resolved, "choice": choice, "reason": entry.reason}
