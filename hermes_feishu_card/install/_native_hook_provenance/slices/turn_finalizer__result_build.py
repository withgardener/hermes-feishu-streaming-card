        "interrupted": interrupted,
        "response_transformed": _response_transformed,
        "response_previewed": getattr(agent, "_response_was_previewed", False),
        "model": agent.model,
        "provider": agent.provider,
        "base_url": agent.base_url,
        "input_tokens": agent.session_input_tokens,
        "output_tokens": agent.session_output_tokens,
        "cache_read_tokens": agent.session_cache_read_tokens,
        "cache_write_tokens": agent.session_cache_write_tokens,
        "reasoning_tokens": agent.session_reasoning_tokens,
        "prompt_tokens": agent.session_prompt_tokens,
        "completion_tokens": agent.session_completion_tokens,
        "total_tokens": agent.session_total_tokens,
        "last_prompt_tokens": getattr(agent.context_compressor, "last_prompt_tokens", 0) or 0,
        "estimated_cost_usd": agent.session_estimated_cost_usd,
        "cost_status": agent.session_cost_status,
        "cost_source": agent.session_cost_source,
        # Requested service tier (from request_overrides.extra_body), for
        # billing audits by callers like `hermes -z --usage-file`.
        "service_tier": (
            (getattr(agent, "request_overrides", {}) or {}).get("extra_body") or {}
        ).get("service_tier"),
        "session_id": agent.session_id,
    }
    if agent._tool_guardrail_halt_decision is not None:
        result["guardrail"] = agent._tool_guardrail_halt_decision.to_metadata()
