    # Plugin hook: post_llm_call
    # Fired once per turn after the tool-calling loop completes.
    # Plugins can use this to persist conversation data (e.g. sync
    # to an external memory system).
    if final_response and not interrupted:
        try:
            from hermes_cli.lifecycle import invoke_hook as _invoke_hook
            _invoke_hook(
                "post_llm_call",
                session_id=agent.session_id,
                task_id=effective_task_id,
                turn_id=turn_id,
                user_message=original_user_message,
                assistant_response=final_response,
                conversation_history=list(messages),
                model=agent.model,
                platform=getattr(agent, "platform", None) or "",
            )
        except Exception as exc:
            logger.warning("post_llm_call hook failed: %s", exc)
