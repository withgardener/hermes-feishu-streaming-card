        # Single-fire contract: pre_tool_call fires exactly once per tool
        # execution. resolve_pre_tool_block() internally calls
        # invoke_hook("pre_tool_call", ...) once and returns the block message
        # for a `block` directive OR for an `approve` directive whose human
        # gate denied/timed-out/errored (fail-closed). Observer plugins see
        # the hook on that same pass. When skip=True, the caller already
        # fired it — do nothing here.
        if not skip_pre_tool_call_hook:
            block_message: Optional[str] = None
            try:
                from hermes_cli.plugins import resolve_pre_tool_block
                block_message = resolve_pre_tool_block(
                    function_name,
                    function_args,
                    task_id=task_id or "",
                    session_id=session_id or "",
                    tool_call_id=tool_call_id or "",
                    turn_id=turn_id or "",
                    api_request_id=api_request_id or "",
                    middleware_trace=list(_tool_middleware_trace),
                )
            except Exception as _hook_err:
                logger.debug("pre_tool_call hook error: %s", _hook_err)

            if block_message is not None:
                result = tool_error(block_message)
                _emit_post_tool_call_hook(
                    function_name=function_name,
                    function_args=function_args,
                    result=result,
                    task_id=task_id,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    turn_id=turn_id,
                    api_request_id=api_request_id,
                    status="blocked",
                    error_type="plugin_block",
                    error_message=block_message,
                    middleware_trace=list(_tool_middleware_trace),
                )
                return result
