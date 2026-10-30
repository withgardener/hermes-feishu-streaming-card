from __future__ import annotations

import ast
from collections.abc import Callable

from .patch_descriptors import PatchGroupDescriptor


_REVISION = "fixed-tag-v2026.8.3-r1"


def _decode(content: bytes) -> tuple[str, str]:
    if type(content) is not bytes:
        raise TypeError("hybrid source must be ordinary bytes")
    text = content.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text, newline


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _marker_block(fragment, indent: str, statements: tuple[str, ...], newline: str) -> str:
    lines = [
        indent + fragment.begin_marker.decode("ascii"),
        *(indent + statement if statement else "" for statement in statements),
        indent + fragment.end_marker.decode("ascii"),
    ]
    return newline.join(lines) + newline


def _insert_at_line(
    content: bytes,
    *,
    anchor: str,
    block: str,
    before: bool,
) -> bytes:
    text, _newline = _decode(content)
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.strip() == anchor]
    if len(matches) != 1:
        raise ValueError(f"fixed-tag anchor mismatch: {anchor}")
    index = matches[0] if before else matches[0] + 1
    lines.insert(index, block)
    rendered = "".join(lines)
    compile(rendered, "<hybrid-fixed-tag>", "exec")
    return rendered.encode("utf-8")


def _insert_in_function(
    content: bytes,
    *,
    function_name: str,
    anchor: str,
    block: str,
    before: bool,
    anchor_indent: str | None = None,
) -> bytes:
    text, _newline = _decode(content)
    tree = ast.parse(text)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(functions) != 1:
        raise ValueError(f"fixed-tag function mismatch: {function_name}")
    function = functions[0]
    lines = text.splitlines(keepends=True)
    matches = [
        index
        for index in range(function.lineno - 1, function.end_lineno or function.lineno)
        if lines[index].strip() == anchor
        and (anchor_indent is None or _indent(lines[index]) == anchor_indent)
    ]
    if len(matches) != 1:
        raise ValueError(f"fixed-tag function anchor mismatch: {function_name}:{anchor}")
    index = matches[0] if before else matches[0] + 1
    lines.insert(index, block)
    rendered = "".join(lines)
    compile(rendered, "<hybrid-fixed-tag>", "exec")
    return rendered.encode("utf-8")


def _insert_after_sequence(content: bytes, sequence: str, block: str) -> bytes:
    text, _newline = _decode(content)
    if text.count(sequence) != 1:
        raise ValueError("fixed-tag sequence anchor mismatch")
    rendered = text.replace(sequence, sequence + block, 1)
    compile(rendered, "<hybrid-fixed-tag>", "exec")
    return rendered.encode("utf-8")


def _remove_fragments(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, _newline = _decode(content)
    lines = text.splitlines(keepends=True)
    for fragment in reversed(descriptor.fragments):
        begin = fragment.begin_marker.decode("ascii")
        end = fragment.end_marker.decode("ascii")
        begins = [index for index, line in enumerate(lines) if line.strip() == begin]
        ends = [index for index, line in enumerate(lines) if line.strip() == end]
        if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
            raise ValueError("hybrid fragment is missing or malformed")
        del lines[begins[0] : ends[0] + 1]
    restored = "".join(lines)
    compile(restored, "<hybrid-fixed-tag>", "exec")
    return restored.encode("utf-8")


def _render_ingress_run(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "_run_start_session_id = session_entry.session_id"
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag ingress anchor missing")
    indent = _indent(line)
    first, second = descriptor.fragments
    first_block = _marker_block(
        first,
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import bind_ingress_from_hermes_locals as _hfc_bind_ingress",
            "    _hfc_platform = getattr(getattr(source, \"platform\", None), \"value\", getattr(source, \"platform\", None))",
            "    _hfc_profile_value = getattr(source, \"profile\", None)",
            "    _hfc_profile_id = _hfc_profile_value if isinstance(_hfc_profile_value, str) and _hfc_profile_value else \"default\"",
            "    _hfc_profile_source = \"locals\" if _hfc_profile_value else \"fallback_default\"",
            "    _hfc_incoming_id = str(getattr(event, \"message_id\", \"\") or self._reply_anchor_for_event(event) or \"\")",
            "    _hfc_reply_id = str(self._reply_anchor_for_event(event) or _hfc_incoming_id)",
            "    _hfc_bind_ingress({",
            "        \"_hfc_authorized\": True,",
            "        \"platform\": _hfc_platform,",
            "        \"profile_id\": _hfc_profile_id,",
            "        \"profile_source\": _hfc_profile_source,",
            "        \"session_id\": _run_start_session_id,",
            "        \"gateway_session_key\": session_key,",
            "        \"generation\": str(run_generation),",
            "        \"chat_id\": str(getattr(source, \"chat_id\", \"\") or \"\"),",
            "        \"incoming_message_id\": _hfc_incoming_id,",
            "        \"reply_to_message_id\": _hfc_reply_id,",
            "        \"thread_id\": str(getattr(source, \"thread_id\", \"\") or \"\"),",
            "    })",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    second_block = _marker_block(
        second,
        indent,
        (
            "# The official pre_llm_call publishes the canonical turn next;",
            "# this marker proves ingress was bound before that lifecycle hook.",
        ),
        newline,
    )
    return _insert_at_line(
        content,
        anchor=anchor,
        block=first_block + second_block,
        before=False,
    )


def _render_turn_publish(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "agent._current_turn_id = turn_id"
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag canonical publish anchor missing")
    indent = _indent(line)
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import publish_canonical_turn_id as _hfc_publish_turn",
            "    _hfc_platform = getattr(getattr(agent, \"platform\", None), \"value\", getattr(agent, \"platform\", None))",
            "    agent._hfc_canonical_turn_token = _hfc_publish_turn(turn_id) if _hfc_platform == \"feishu\" else None",
            "except Exception:",
            "    agent._hfc_canonical_turn_token = None",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=False)


def _render_turn_clear(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "agent._turn_received_provider_response = False"
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag canonical clear anchor missing")
    indent = _indent(line)
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import consume_terminal_record_from_hermes_locals as _hfc_take_terminal",
            "    from hermes_feishu_card.hook_runtime import clear_canonical_turn_id as _hfc_clear_turn",
            "    _hfc_platform = getattr(getattr(agent, \"platform\", None), \"value\", getattr(agent, \"platform\", None))",
            "    if _hfc_platform == \"feishu\":",
            "        _hfc_terminal_record = _hfc_take_terminal({\"_hfc_authorized\": True, \"platform\": \"feishu\", \"turn_id\": turn_id})",
            "        if _hfc_terminal_record is not None:",
            "            result[\"_hfc_terminal_record\"] = _hfc_terminal_record",
            "    _hfc_turn_token = getattr(agent, \"_hfc_canonical_turn_token\", None)",
            "    if _hfc_turn_token is not None:",
            "        _hfc_clear_turn(_hfc_turn_token)",
            "    agent._hfc_canonical_turn_token = None",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=False)


def _render_terminal_gateway(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = 'response = agent_result.get("final_response") or ""'
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag terminal delivery anchor missing")
    indent = _indent(line)
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import apply_hybrid_terminal_record as _hfc_apply_terminal",
            "    _hfc_delivery_decision = _hfc_apply_terminal(agent_result.pop(\"_hfc_terminal_record\", None))",
            "    if _hfc_delivery_decision == \"card\":",
            "        response = \"\"",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=False)


def _render_answer_delta(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "def _interim_assistant_cb(text: str, *, already_streamed: bool = False) -> None:"
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag answer callback anchor missing")
    indent = _indent(line)
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "_hfc_native_stream_delta_cb = _stream_delta_cb",
            "def _stream_delta_cb(text: str) -> None:",
            "    try:",
            "        from hermes_feishu_card.hook_runtime import emit_delta_from_hermes_locals_threadsafe as _hfc_emit_delta",
            "        if _hfc_emit_delta({\"_hfc_authorized\": True, \"platform\": \"feishu\", \"turn_id\": str(getattr(agent, \"_current_turn_id\", \"\") or \"\"), \"text\": text}, \"answer.delta\"):",
            "            return",
            "    except Exception:",
            "        pass",
            "    if _hfc_native_stream_delta_cb is not None:",
            "        _hfc_native_stream_delta_cb(text)",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=True)


def _render_thinking_delta(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "def _interim_assistant_cb(text: str, *, already_streamed: bool = False) -> None:"
    line = next((item for item in text.splitlines() if item.strip() == anchor), None)
    if line is None:
        raise ValueError("fixed-tag thinking callback anchor missing")
    indent = _indent(line) + "    "
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import emit_delta_from_hermes_locals_threadsafe as _hfc_emit_delta",
            "    if not already_streamed and _hfc_emit_delta({\"_hfc_authorized\": True, \"platform\": \"feishu\", \"turn_id\": str(getattr(agent, \"_current_turn_id\", \"\") or \"\"), \"text\": text}, \"thinking.delta\"):",
            "        return",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=False)


def _render_status_notice(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "ctx = self._ctx"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef) and node.name == "_status_callback_sync"
    )
    line = text.splitlines()[function.lineno]
    indent = _indent(line)
    block = _marker_block(
        descriptor.fragments[0],
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import submit_status_notice_from_hermes_locals as _hfc_status_notice",
            "    if _hfc_status_notice({\"_hfc_authorized\": True, \"platform\": \"feishu\"}, event_type=event_type, message=message):",
            "        return",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_status_callback_sync",
        anchor=anchor,
        block=block,
        before=False,
    )


def _render_command_card_startup(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "await self._redeliver_pending_obligations()"
    line = next(item for item in text.splitlines() if item.strip() == anchor)
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import install_feishu_command_card_adapter_methods as _hfc_install_command_cards",
            "    _hfc_install_command_cards(self)",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=True)


def _render_command_card_adapter(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "source = event.source"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_message"
    )
    line = text.splitlines()[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if text.splitlines()[index].strip() == anchor
        )
    ]
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import install_feishu_command_card_adapter_methods as _hfc_install_command_cards",
            "    _hfc_install_command_cards(self, event=event)",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_handle_message",
        anchor=anchor,
        block=block,
        before=False,
        anchor_indent=_indent(line),
    )


def _render_native_redelivery(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "result = await adapter.send("
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_redeliver_pending_obligations"
    )
    lines = text.splitlines()
    line = lines[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if lines[index].strip() == anchor
        )
    ]
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import prepare_native_handoff_recovery as _hfc_prepare_native_handoff_recovery",
            "    await _hfc_prepare_native_handoff_recovery(",
            "        adapter=adapter, obligation_id=row.get(\"obligation_id\"),",
            "        chat_id=row.get(\"chat_id\"), content=content,",
            "        original_content=row.get(\"content\"), thread_id=row.get(\"thread_id\") or \"\",",
            "    )",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_redeliver_pending_obligations",
        anchor=anchor,
        block=block,
        before=True,
    )


def _render_platform_notice(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = '"""Deliver a setup/operational notice using platform-specific privacy rules."""'
    line = next(item for item in text.splitlines() if item.strip() == anchor)
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import handle_platform_notice_from_hermes as _hfc_handle_platform_notice",
            "    if _hfc_handle_platform_notice(self, source, content):",
            "        return None",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=False)


def _render_hfc_command(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "_quick_key = self._session_key_for_source(source)"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_message"
    )
    lines = text.splitlines()
    line = lines[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if lines[index].strip() == anchor
        )
    ]
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import maintenance_admission_from_hermes_locals as _hfc_maintenance_admission",
            "    if await _hfc_maintenance_admission(locals()):",
            "        return None",
            "    from hermes_feishu_card.hook_runtime import handle_hfc_command_from_hermes_locals as _hfc_handle_command",
            "    _hfc_message_id = self._reply_anchor_for_event(event) or getattr(event, \"message_id\", None)",
            "    if _hfc_handle_command({**locals(), \"message_id\": _hfc_message_id}):",
            "        return None",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_handle_message",
        anchor=anchor,
        block=block,
        before=False,
    )


def _render_cron_delivery(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef) and node.name == "_deliver_result"
    )
    lines = text.splitlines()
    line = lines[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if lines[index].strip() == anchor
        )
    ]
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import emit_cron_delivery as _hfc_emit_cron",
            "    _hfc_cron_metadata = {\"delivery_kind\": \"cron\"}",
            "    if _hfc_emit_cron({**locals(), \"_hfc_resolved_targets\": locals().get(\"targets\", [])}):",
            "        if media_files:",
            "            cleaned_delivery_content = \"\"",
            "        else:",
            "            return None",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_deliver_result",
        anchor=anchor,
        block=block,
        before=False,
    )


def _render_exact_base_no_text(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "if text_content and not _tts_caption_delivered:"
    line = next(item for item in text.splitlines() if item.strip() == anchor)
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import finalize_exact_base_no_text as _hfc_finalize_no_text",
            "    if not text_content or _tts_caption_delivered:",
            "        await _hfc_finalize_no_text({**locals(), \"source\": event.source})",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=True)


def _render_exact_base_final_delivery(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "result = await delivery_adapter._send_with_retry("
    line = next(item for item in text.splitlines() if item.strip() == anchor)
    block = _marker_block(
        descriptor.fragments[0],
        _indent(line),
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import prepare_exact_base_final_delivery as _hfc_prepare_final_delivery",
            "    delivery_adapter, text_content, _reply_anchor, _final_thread_metadata = await _hfc_prepare_final_delivery({",
            "        **locals(), \"source\": event.source, \"delivery_adapter\": delivery_adapter,",
            "        \"content\": text_content, \"obligation_id\": _obligation_id,",
            "        \"reply_to\": _reply_anchor, \"metadata\": _final_thread_metadata,",
            "    })",
            "except Exception:",
            "    pass",
        ),
        newline,
    )
    return _insert_at_line(content, anchor=anchor, block=block, before=True)


def _render_clarify_round_trip(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    _text, newline = _decode(content)
    indent = " " * 12
    register_fragment, resolve_fragment = descriptor.fragments
    register_block = _marker_block(
        register_fragment,
        indent,
        (
            "_hfc_clarify_entry = _clarify_mod.get_pending_for_session(ctx.session_key or \"\", include_choice_prompts=True)",
            "_hfc_clarify_owned = False",
            "try:",
            "    from hashlib import sha256 as _hfc_sha256",
            "    _hfc_clarify_fingerprint = _hfc_sha256((str(question) + \"\\0\" + repr(list(choices) if choices else []) + \"\\0\" + str(bool(multi_select))).encode(\"utf-8\")).hexdigest()",
            "    def _hfc_resolve_clarify(selected_value):",
            "        return _clarify_mod.resolve_gateway_clarify(clarify_id, selected_value)",
            "except Exception:",
            "    _hfc_clarify_entry = None",
        ),
        newline,
    )
    resolve_block = _marker_block(
        resolve_fragment,
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import admit_pending_interaction_from_hermes_locals as _hfc_admit_interaction",
            "    if _hfc_clarify_entry is not None:",
            "        _hfc_clarify_timeout = _clarify_mod.get_clarify_timeout()",
            "        _hfc_clarify_owned = _hfc_admit_interaction(",
            "            {\"_hfc_authorized\": True, \"platform\": \"feishu\", \"turn_id\": str(getattr(agent, \"_current_turn_id\", \"\") or \"\")}, \"clarify\",",
            "            {\"session_identity\": ctx.session_key or ctx._status_chat_id, \"interaction_id\": clarify_id, \"fingerprint\": _hfc_clarify_fingerprint},",
            "            _hfc_clarify_entry, _hfc_resolve_clarify,",
            "            {\"prompt\": str(question), \"description\": \"\", \"allow_custom_input\": True,",
            "             \"multi_select\": bool(multi_select), \"timeout_seconds\": float(_hfc_clarify_timeout),",
            "             \"options\": [{\"label\": str(item), \"value\": str(item), \"style\": \"default\"} for item in (list(choices) if choices else [])]},",
            "        )",
            "    if _hfc_clarify_owned:",
            "        try:",
            "            ctx._status_adapter.pause_typing_for_chat(ctx._status_chat_id)",
            "        except Exception:",
            "            pass",
            "        _hfc_clarify_response = _clarify_mod.wait_for_response(clarify_id, timeout=float(_hfc_clarify_timeout))",
            "        if _hfc_clarify_response is None or _hfc_clarify_response == \"\":",
            "            return f\"[user did not respond within {int(_hfc_clarify_timeout / 60)}m]\"",
            "        return _hfc_clarify_response",
            "except Exception:",
            "    _hfc_clarify_owned = False",
        ),
        newline,
    )
    sequence = (
        "                multi_select=bool(multi_select)," + newline
        + "            )" + newline
    )
    return _insert_after_sequence(
        content,
        sequence,
        register_block + resolve_block,
    )


def _render_approval_round_trip(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "_gateway_queues.setdefault(session_key, []).append(entry)"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef) and node.name == "_await_gateway_decision"
    )
    lines = text.splitlines()
    line = lines[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if lines[index].strip() == anchor
        )
    ]
    indent = _indent(line)
    register_fragment, resolve_fragment = descriptor.fragments
    register_block = _marker_block(
        register_fragment,
        indent,
        (
            "_hfc_approval_owned = False",
            "try:",
            "    from hashlib import sha256 as _hfc_sha256",
            "    _hfc_approval_command = \" \".join(str(command).split())",
            "    _hfc_approval_fingerprint = _hfc_sha256(_hfc_approval_command.encode(\"utf-8\")).hexdigest()",
            "    _hfc_approval_tool_call_id = _approval_tool_call_id.get()",
            "    _hfc_approval_interaction_id = \"approval:\" + str(_approval_turn_id.get()) + \":\" + str(_hfc_approval_tool_call_id) + \":\" + _hfc_approval_fingerprint[:16]",
            "    def _hfc_resolve_approval(selected_value):",
            "        if selected_value not in {\"once\", \"session\", \"always\", \"deny\"}:",
            "            return False",
            "        with _lock:",
            "            _hfc_queue = _gateway_queues.get(session_key, [])",
            "            if entry not in _hfc_queue or entry.event.is_set():",
            "                return False",
            "            entry.result = selected_value",
            "            entry.event.set()",
            "            return True",
            "except Exception:",
            "    _hfc_approval_interaction_id = \"\"",
        ),
        newline,
    )
    resolve_block = _marker_block(
        resolve_fragment,
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import admit_pending_interaction_from_hermes_locals as _hfc_admit_interaction",
            "    _hfc_approval_options = [{\"label\": \"允许一次\", \"value\": \"once\", \"style\": \"primary\"}]",
            "    if approval_data.get(\"allow_session\", True):",
            "        _hfc_approval_options.append({\"label\": \"本会话允许\", \"value\": \"session\", \"style\": \"default\"})",
            "    if approval_data.get(\"allow_permanent\", True):",
            "        _hfc_approval_options.append({\"label\": \"始终允许\", \"value\": \"always\", \"style\": \"default\"})",
            "    _hfc_approval_options.append({\"label\": \"拒绝\", \"value\": \"deny\", \"style\": \"danger\"})",
            "    if _hfc_approval_interaction_id:",
            "        _hfc_approval_owned = _hfc_admit_interaction(",
            "            {\"_hfc_authorized\": True, \"platform\": \"feishu\", \"turn_id\": str(_approval_turn_id.get() or \"\")}, \"approval\",",
            "            {\"session_identity\": session_key, \"interaction_id\": _hfc_approval_interaction_id, \"fingerprint\": _hfc_approval_fingerprint},",
            "            entry, _hfc_resolve_approval,",
            "            {\"prompt\": \"需要授权后继续执行\", \"description\": str(description),",
            "             \"allow_custom_input\": False, \"multi_select\": False,",
            "             \"timeout_seconds\": float(_get_approval_timeout()), \"options\": _hfc_approval_options},",
            "        )",
            "    if _hfc_approval_owned:",
            "        notify_cb = lambda _approval_data: None",
            "except Exception:",
            "    _hfc_approval_owned = False",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_await_gateway_decision",
        anchor=anchor,
        block=register_block + resolve_block,
        before=False,
    )


def _render_slash_confirm(content: bytes, descriptor: PatchGroupDescriptor) -> bytes:
    text, newline = _decode(content)
    anchor = "_slash_confirm_mod.register(session_key, confirm_id, command, handler)"
    function = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_request_slash_confirm"
    )
    lines = text.splitlines()
    line = lines[
        next(
            index
            for index in range(function.lineno - 1, function.end_lineno or function.lineno)
            if lines[index].strip() == anchor
        )
    ]
    indent = _indent(line)
    register_fragment, resolve_fragment = descriptor.fragments
    register_block = _marker_block(
        register_fragment,
        indent,
        (
            "_hfc_slash_owned = False",
            "try:",
            "    import asyncio as _hfc_asyncio",
            "    from hashlib import sha256 as _hfc_sha256",
            "    _hfc_slash_loop = _hfc_asyncio.get_running_loop()",
            "    with _slash_confirm_mod._lock:",
            "        _hfc_slash_pending = _slash_confirm_mod._pending.get(session_key)",
            "    _hfc_slash_fingerprint = _hfc_sha256((str(session_key) + \"\\0\" + str(confirm_id) + \"\\0\" + str(command)).encode(\"utf-8\")).hexdigest()",
            "    def _hfc_resolve_slash(selected_value):",
            "        if selected_value not in {\"once\", \"always\", \"cancel\"}:",
            "            return False",
            "        _hfc_asyncio.run_coroutine_threadsafe(_slash_confirm_mod.resolve(session_key, confirm_id, selected_value), _hfc_slash_loop)",
            "        return True",
            "except Exception:",
            "    _hfc_slash_pending = None",
        ),
        newline,
    )
    resolve_block = _marker_block(
        resolve_fragment,
        indent,
        (
            "try:",
            "    from hermes_feishu_card.hook_runtime import admit_pending_interaction_from_hermes_locals as _hfc_admit_interaction",
            "    if _hfc_slash_pending is not None:",
            "        _hfc_slash_owned = _hfc_admit_interaction(",
            "            {\"_hfc_authorized\": True, \"platform\": \"feishu\"}, \"slash\",",
            "            {\"session_identity\": session_key, \"interaction_id\": \"slash:\" + str(session_key) + \":\" + str(confirm_id), \"fingerprint\": _hfc_slash_fingerprint},",
            "            _hfc_slash_pending, _hfc_resolve_slash,",
            "            {\"prompt\": str(title), \"description\": str(message), \"allow_custom_input\": False,",
            "             \"multi_select\": False, \"timeout_seconds\": 300.0,",
            "             \"options\": [{\"label\": \"允许一次\", \"value\": \"once\", \"style\": \"primary\"},",
            "                         {\"label\": \"始终允许\", \"value\": \"always\", \"style\": \"default\"},",
            "                         {\"label\": \"取消\", \"value\": \"cancel\", \"style\": \"danger\"}]},",
            "        )",
            "    if _hfc_slash_owned:",
            "        return None",
            "except Exception:",
            "    _hfc_slash_owned = False",
        ),
        newline,
    )
    return _insert_in_function(
        content,
        function_name="_request_slash_confirm",
        anchor=anchor,
        block=register_block + resolve_block,
        before=False,
    )


def _render_subagent_parent_identity(
    content: bytes,
    descriptor: PatchGroupDescriptor,
) -> bytes:
    text, newline = _decode(content)
    tree = ast.parse(text)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_finalize_child_results"
    )
    original = 'parent_turn_id=getattr(parent_agent, "_current_turn_id", "") or "",'
    lines = text.splitlines(keepends=True)
    matches = [
        index
        for index in range(function.lineno - 1, function.end_lineno or function.lineno)
        if lines[index].strip() == original
    ]
    if len(matches) != 1:
        raise ValueError("fixed-tag immutable parent anchor mismatch")
    index = matches[0]
    indent = _indent(lines[index])
    lines[index] = _marker_block(
        descriptor.fragments[0],
        indent,
        ('parent_turn_id=getattr(child, "_parent_turn_id", "") or "",',),
        newline,
    )
    rendered = "".join(lines)
    compile(rendered, "<hybrid-fixed-tag>", "exec")
    return rendered.encode("utf-8")


def _remove_subagent_parent_identity(
    content: bytes,
    descriptor: PatchGroupDescriptor,
) -> bytes:
    text, newline = _decode(content)
    lines = text.splitlines(keepends=True)
    fragment = descriptor.fragments[0]
    begin = fragment.begin_marker.decode("ascii")
    end = fragment.end_marker.decode("ascii")
    begins = [index for index, line in enumerate(lines) if line.strip() == begin]
    ends = [index for index, line in enumerate(lines) if line.strip() == end]
    if len(begins) != 1 or len(ends) != 1 or ends[0] != begins[0] + 2:
        raise ValueError("immutable parent patch is missing or malformed")
    indent = _indent(lines[begins[0]])
    expected = 'parent_turn_id=getattr(child, "_parent_turn_id", "") or "",'
    if lines[begins[0] + 1].strip() != expected:
        raise ValueError("immutable parent patch body changed")
    lines[begins[0] : ends[0] + 1] = [
        indent
        + 'parent_turn_id=getattr(parent_agent, "_current_turn_id", "") or "",'
        + newline
    ]
    restored = "".join(lines)
    compile(restored, "<hybrid-fixed-tag>", "exec")
    return restored.encode("utf-8")


_RENDERERS: dict[tuple[str, str], Callable[[bytes, PatchGroupDescriptor], bytes]] = {
    ("ingress_binding", "gateway/run.py"): _render_ingress_run,
    ("ingress_binding", "agent/turn_context.py"): _render_turn_publish,
    ("ingress_binding", "agent/turn_finalizer.py"): _render_turn_clear,
    ("terminal_disposition", "gateway/run.py"): _render_terminal_gateway,
    ("answer_delta", "gateway/run.py"): _render_answer_delta,
    ("thinking_delta", "gateway/run.py"): _render_thinking_delta,
    ("status_notice", "gateway/run.py"): _render_status_notice,
    ("command_card_startup", "gateway/run.py"): _render_command_card_startup,
    ("command_card_adapter", "gateway/run.py"): _render_command_card_adapter,
    ("native_redelivery", "gateway/run.py"): _render_native_redelivery,
    ("platform_notice", "gateway/run.py"): _render_platform_notice,
    ("hfc_command", "gateway/run.py"): _render_hfc_command,
    ("cron_delivery", "cron/scheduler.py"): _render_cron_delivery,
    ("exact_base_no_text", "gateway/platforms/base.py"): _render_exact_base_no_text,
    ("exact_base_final_delivery", "gateway/platforms/base.py"): _render_exact_base_final_delivery,
    ("clarify_round_trip", "gateway/run.py"): _render_clarify_round_trip,
    ("approval_round_trip", "tools/approval.py"): _render_approval_round_trip,
    ("slash_confirm", "gateway/run.py"): _render_slash_confirm,
    ("subagent_parent_identity", "tools/delegate_tool.py"): _render_subagent_parent_identity,
}

_REMOVERS: dict[
    tuple[str, str], Callable[[bytes, PatchGroupDescriptor], bytes]
] = {
    (
        "subagent_parent_identity",
        "tools/delegate_tool.py",
    ): _remove_subagent_parent_identity,
}


def reviewed_descriptors(
    descriptors: tuple[PatchGroupDescriptor, ...],
) -> tuple[PatchGroupDescriptor, ...]:
    reviewed: list[PatchGroupDescriptor] = []
    for descriptor in descriptors:
        implementation = _RENDERERS.get((descriptor.group, descriptor.target))
        if implementation is None:
            reviewed.append(descriptor)
            continue

        def render(content: bytes, *, _descriptor=descriptor, _implementation=implementation) -> bytes:
            return _implementation(content, _descriptor)

        remover = _REMOVERS.get((descriptor.group, descriptor.target))

        def remove(
            content: bytes,
            *,
            _descriptor=descriptor,
            _remover=remover,
        ) -> bytes:
            if _remover is not None:
                return _remover(content, _descriptor)
            return _remove_fragments(content, _descriptor)

        reviewed.append(
            PatchGroupDescriptor(
                group=descriptor.group,
                target=descriptor.target,
                fragments=descriptor.fragments,
                renderer=render,
                remover=remove,
                renderer_revision=_REVISION,
            )
        )
    return tuple(reviewed)
