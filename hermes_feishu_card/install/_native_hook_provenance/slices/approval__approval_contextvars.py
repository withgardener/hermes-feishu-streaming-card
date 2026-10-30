_approval_session_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "approval_session_key",
    default="",
)
_approval_turn_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "approval_turn_id",
    default="",
)
_approval_tool_call_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "approval_tool_call_id",
    default="",
)
