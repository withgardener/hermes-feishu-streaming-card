    """Restore the prior approval session key context."""
    _approval_session_key.reset(token)


def set_current_observability_context(
    *,
    turn_id: str = "",
    tool_call_id: str = "",
) -> tuple[contextvars.Token[str], contextvars.Token[str]]:
    """Bind active tool correlation IDs to approval hooks."""
    return (
        _approval_turn_id.set(turn_id or ""),
        _approval_tool_call_id.set(tool_call_id or ""),
    )


def reset_current_observability_context(
    tokens: tuple[contextvars.Token[str], contextvars.Token[str]],
) -> None:
    """Restore prior approval hook correlation IDs."""
    turn_token, tool_token = tokens
    _approval_tool_call_id.reset(tool_token)
    _approval_turn_id.reset(turn_token)
