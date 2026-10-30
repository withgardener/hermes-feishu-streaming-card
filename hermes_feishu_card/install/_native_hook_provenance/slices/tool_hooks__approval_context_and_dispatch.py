        # Measure tool dispatch latency so post_tool_call and
        # transform_tool_result hooks can observe per-tool duration.
        # Inspired by Claude Code 2.1.119, which added ``duration_ms`` to
        # PostToolUse hook inputs so plugin authors can build latency
        # dashboards, budget alerts, and regression canaries without having
        # to wrap every tool manually.  We use monotonic() so the value is
        # unaffected by wall-clock adjustments during the call.
        _dispatch_start = time.monotonic()
        _approval_tokens = None
        try:
            from tools.approval import (
                reset_current_observability_context,
                set_current_observability_context,
            )
            _approval_tokens = set_current_observability_context(
                turn_id=turn_id or "",
                tool_call_id=tool_call_id or "",
            )
        except Exception:
            reset_current_observability_context = None
        try:
            if function_name == "execute_code":
                # Prefer the caller-provided list so subagents can't overwrite
                # the parent's tool set via the process-global.
                sandbox_enabled = enabled_tools if enabled_tools is not None else _last_resolved_tool_names
                def _dispatch(next_args: Dict[str, Any]) -> Any:
                    return registry.dispatch(
                        function_name, next_args,
                        task_id=task_id,
                        session_id=session_id,
                        enabled_tools=sandbox_enabled,
                    )
            else:
                def _dispatch(next_args: Dict[str, Any]) -> Any:
                    return registry.dispatch(
                        function_name, next_args,
                        task_id=task_id,
                        session_id=session_id,
                        user_task=user_task,
                    )
            if skip_tool_execution_middleware:
                result = _dispatch(function_args)
            else:
                from hermes_cli.middleware import run_tool_execution_middleware

                result = run_tool_execution_middleware(
                    function_name,
                    function_args,
                    _dispatch,
                    original_args=_tool_original_args,
                    task_id=task_id or "",
                    session_id=session_id or "",
                    tool_call_id=tool_call_id or "",
                    turn_id=turn_id or "",
                    api_request_id=api_request_id or "",
                )
        finally:
            if _approval_tokens is not None and reset_current_observability_context is not None:
                try:
                    reset_current_observability_context(_approval_tokens)
                except Exception:
                    pass
        duration_ms = int((time.monotonic() - _dispatch_start) * 1000)

        _emit_post_tool_call_hook(
            function_name=function_name,
            function_args=function_args,
            result=result,
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            turn_id=turn_id,
            api_request_id=api_request_id,
            duration_ms=duration_ms,
            middleware_trace=list(_tool_middleware_trace),
        )
