"""Verify monolithic, decomposed and split BasePlatformAdapter contracts.

Returns exact insertion coordinates only after checking executable call order.
Owned ledger fragments are supplied by the patcher's existing renderer; this
module does not choose or apply a patch and does not import the coordinator.
"""
from __future__ import annotations

import ast
from typing import Any

from .ast_contracts import (
    _call_function,
    _direct_child_position,
    _exact_deliver_attachments,
    _is_exact_assignment_call,
    _is_exact_compute_obligation_assignment,
    _is_exact_constant_assignment,
    _is_exact_final_send_assignment,
    _is_exact_ledger_call,
    _is_exact_local_filter_assignment,
    _is_exact_mark_failed_call,
    _is_exact_media_filter_assignment,
    _is_exact_name_assignment,
    _is_exact_positional_call,
    _is_split_compute_obligation_assignment,
    _is_split_final_send_assignment,
    _is_split_finalize_obligation_call,
    _is_split_record_obligation_call,
    _is_strip_assignment,
    _line_indent,
    _same_expression,
    _unique_exact_base_node,
)


def _parse_exact_base_content(content: str) -> ast.Module:
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise ValueError("could not find safe BasePlatformAdapter contract") from exc
    return tree


def find_base_patch_locations(
    tree: ast.Module, lines: list[str], *, owned_ledger_blocks: tuple[str, ...] = (),
) -> tuple[tuple[int, str], tuple[int, str]]:
    """Return the two insertion locations after validating Hermes' pipeline."""
    if _has_split_exact_base(tree):
        if _has_decomposed_base(tree):
            return _find_split_decomposed_base_patch_locations(tree, lines, owned_ledger_blocks=owned_ledger_blocks)
        # Only the reported decomposed layout has a verified split contract.
        raise ValueError("could not find safe BasePlatformAdapter contract")
    if _has_decomposed_base(tree):
        return _find_decomposed_base_patch_locations(tree, lines)
    method = _find_exact_base_process_method(tree)
    method_nodes = list(ast.walk(method))

    extract_media = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("media_files", "response"),
            owner="self",
            function="extract_media",
            args=("response",),
        ),
    )
    filter_media = _unique_exact_base_node(
        method_nodes,
        _is_exact_media_filter_assignment,
    )
    extract_images = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("images", "text_content"),
            owner="self",
            function="extract_images",
            args=("response",),
        ),
    )
    strip_text = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_strip_assignment(
            node,
            target="text_content",
            source="text_content",
        ),
    )
    extract_local = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("local_files", "text_content"),
            owner="self",
            function="extract_local_files",
            args=("text_content",),
        ),
    )
    filter_local = _unique_exact_base_node(
        method_nodes,
        _is_exact_local_filter_assignment,
    )
    recovered = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_strip_assignment(
            node,
            target="_recovered",
            source="response",
        ),
    )
    restore_text = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_name_assignment(
            node,
            target="text_content",
            value="_recovered",
        ),
    )
    final_metadata = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("_final_thread_metadata",),
            owner=None,
            function="_mark_notify_metadata",
            args=("_thread_metadata",),
        ),
    )
    tts_caption_default = _unique_exact_base_node(
        method_nodes,
        lambda node: _is_exact_constant_assignment(
            node,
            target="_tts_caption_delivered",
            value=False,
        ),
    )
    text_guard = _unique_exact_base_node(
        method_nodes,
        lambda node: isinstance(node, ast.If)
        and _same_expression(
            node.test,
            "text_content and not _tts_caption_delivered",
        ),
    )

    guard_nodes = list(ast.walk(text_guard))
    delivery_adapter = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("delivery_adapter",),
            owner="self",
            function="_final_delivery_adapter",
            args=("event.source",),
        ),
    )
    reply_anchor = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_assignment_call(
            node,
            targets=("_reply_anchor",),
            owner=None,
            function="_reply_anchor_for_event",
            args=("event",),
        ),
    )
    compute_obligation = _unique_exact_base_node(
        guard_nodes,
        _is_exact_compute_obligation_assignment,
    )
    obligation_default = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_constant_assignment(
            node,
            target="_obligation_id",
            value=None,
        )
        and node.lineno < compute_obligation.lineno,
    )
    record_obligation = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_ledger_call(
            node,
            function="record_obligation",
            required_keywords={
                "obligation_id": "_obligation_id",
                "content": "text_content",
            },
        ),
    )
    mark_attempting = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_positional_call(
            node,
            function="mark_attempting",
            args=("_obligation_id",),
        ),
    )
    send = _unique_exact_base_node(guard_nodes, _is_exact_final_send_assignment)
    record_delivery = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_positional_call(
            node,
            function="_record_delivery",
            args=("result",),
        ),
    )
    mark_delivered = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_positional_call(
            node,
            function="mark_delivered",
            args=("_obligation_id",),
        ),
    )
    mark_failed = _unique_exact_base_node(
        guard_nodes,
        lambda node: _is_exact_mark_failed_call(node),
    )

    # The ledger operations must finish in one direct child statement before
    # the send. Merely checking line order would accept a source drift where
    # `_send_with_retry` moved inside the ledger try, reopening the exact crash
    # window this patch is meant to close.
    send_position = _direct_child_position(text_guard.body, send)
    ledger_positions = {
        _direct_child_position(text_guard.body, node)
        for node in (compute_obligation, record_obligation, mark_attempting)
    }
    if (
        send_position is None
        or None in ledger_positions
        or len(ledger_positions) != 1
        or next(iter(ledger_positions)) >= send_position
    ):
        raise ValueError("could not find safe BasePlatformAdapter contract")

    ordered = (
        extract_media,
        filter_media,
        extract_images,
        strip_text,
        extract_local,
        filter_local,
        recovered,
        restore_text,
        final_metadata,
        tts_caption_default,
        text_guard,
        delivery_adapter,
        reply_anchor,
        obligation_default,
        compute_obligation,
        record_obligation,
        mark_attempting,
        send,
        record_delivery,
        mark_delivered,
        mark_failed,
    )
    if any(getattr(node, "lineno", None) is None for node in ordered):
        raise ValueError("could not find safe BasePlatformAdapter contract")
    line_numbers = [node.lineno for node in ordered]
    if line_numbers != sorted(line_numbers) or len(set(line_numbers)) != len(line_numbers):
        raise ValueError("could not find safe BasePlatformAdapter contract")

    no_text_index = text_guard.lineno - 1
    send_index = send.lineno - 1
    return (
        (no_text_index, _line_indent(lines, no_text_index)),
        (send_index, _line_indent(lines, send_index)),
    )


def _has_split_exact_base(tree: Any) -> bool:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BasePlatformAdapter"
    ]
    return len(classes) == 1 and sum(
        isinstance(node, ast.AsyncFunctionDef) and node.name == "send_final_ledgered"
        for node in classes[0].body
    ) == 1


def _validate_split_ledger_bracket(ledger: ast.AsyncFunctionDef, owned_ledger_blocks: tuple[str, ...]) -> None:
    """Require an executable, contiguous ledger bracket, not just ordered AST hits."""
    expected = ast.parse("""
delivery_adapter = self._final_delivery_adapter(event.source)
obligation_id = await self._record_delivery_obligation(event, session_key, text_content, delivery_adapter, is_ephemeral_response)
result = await delivery_adapter._send_with_retry(chat_id=event.source.chat_id, content=text_content, reply_to=reply_to, metadata=metadata)
if obligation_id is not None:
    await self._finalize_delivery_obligation(obligation_id, result, event, delivery_adapter)
return result, delivery_adapter
""").body
    body: list[ast.stmt] = []
    # Hermes may hand crash recovery from the turn marker to the ledger here.
    # Accept only this exact optional guard, once, after recording and before
    # sending. Keep it in generated source; never weaken the delivery bracket.
    release_guard = ast.parse("if obligation_id is not None:\n    await self._release_turn_marker(event)").body[0]
    release_seen = False
    # Hermes records reply latency after the actual send and before finalizing
    # the obligation. Preserve exactly this optional synchronous call, once.
    clock_stop = ast.parse("stop_reply_clock(delivery_adapter, event.source.chat_id, result)").body[0]
    clock_seen = False
    for index, node in enumerate(ledger.body):
        if len(body) == 3 and not clock_seen and ast.dump(node) == ast.dump(clock_stop):
            clock_seen = True
            continue
        if len(body) == 2 and not release_seen and ast.dump(node) == ast.dump(release_guard):
            release_seen = True
            continue
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        # The upstream informational log between adapter selection and recording
        # is the only non-contract statement accepted at this seam.
        if (len(body) == 1 and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and _call_function(node.value) == ("logger", "info")):
            continue
        if len(body) == 2 and any(
            ast.dump(node) == ast.dump(ast.parse(block).body[0])
            for block in owned_ledger_blocks
        ):
            continue
        body.append(node)
    args = ledger.args
    if (args.vararg or args.kwarg or args.posonlyargs
            or [ast.dump(n) for n in body] != [ast.dump(n) for n in expected]):
        raise ValueError("could not find safe BasePlatformAdapter contract")


def _find_exact_base_process_method(tree: ast.Module) -> ast.AsyncFunctionDef:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BasePlatformAdapter"
    ]
    if len(classes) != 1:
        raise ValueError("could not find safe BasePlatformAdapter contract")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_process_message_background"
    ]
    if len(methods) != 1:
        raise ValueError("could not find safe BasePlatformAdapter contract")
    return methods[0]


def _has_decomposed_base(tree: ast.Module) -> bool:
    return any(isinstance(c, ast.ClassDef) and c.name == "BasePlatformAdapter"
               and any(isinstance(n, ast.AsyncFunctionDef) and n.name == "_send_final_text" for n in c.body)
               for c in tree.body)


def _find_decomposed_base_patch_locations(tree: ast.Module, lines: list[str]) -> tuple[tuple[int, str], tuple[int, str]]:
    """Verify the extracted methods AND their exact call/argument boundaries."""
    error = "could not find safe BasePlatformAdapter contract"
    process = _find_exact_base_process_method(tree)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BasePlatformAdapter")
    def method(name: Any) -> Any:
        matches = [n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
        if len(matches) != 1:
            raise ValueError(error)
        return matches[0]
    extract, send, record, finish = (method(n) for n in (
        "_extract_response_content", "_send_final_text", "_record_delivery_obligation", "_finalize_delivery_obligation"))
    # Positional calls are only safe when the callee binds the same values.
    # Matching names somewhere in the body does not prove that boundary.
    for node, positional, keyword_only in (
        (process, ("self", "event", "session_key"), ()),
        (extract, ("self", "response", "event", "session_key"), ("is_ephemeral_response",)),
        (send, ("self", "event", "session_key", "text_content", "metadata",
                "is_ephemeral_response", "ephemeral_ttl", "record_delivery"), ()),
        (record, ("self", "event", "session_key", "text_content", "delivery_adapter",
                  "is_ephemeral_response"), ()),
        (finish, ("self", "obligation_id", "result", "event", "delivery_adapter"), ()),
    ):
        args = node.args
        if (tuple(a.arg for a in (*args.posonlyargs, *args.args)) != positional
                or tuple(a.arg for a in args.kwonlyargs) != keyword_only
                or args.vararg is not None or args.kwarg is not None):
            raise ValueError(error)
    def exact(scope: Any, source: Any) -> Any:
        expected = ast.parse(source).body[0]
        return _unique_exact_base_node(ast.walk(scope), lambda n: ast.dump(n) == ast.dump(expected))
    def ordered(nodes: Any) -> Any:
        if any(a.lineno >= b.lineno for a, b in zip(nodes, nodes[1:])):
            raise ValueError(error)
    extracted = exact(process, 'extracted = await self._extract_response_content(response, event, session_key, is_ephemeral_response=is_ephemeral_response)')
    assigned = exact(process, 'text_content, media_files = extracted.text_content, extracted.media_files')
    metadata = exact(process, '_final_thread_metadata = _mark_notify_metadata(_thread_metadata)')
    tts_default = exact(process, '_tts_caption_delivered = False')
    guard = _unique_exact_base_node(ast.walk(process), lambda n: isinstance(n, ast.If) and _same_expression(n.test, 'text_content and not _tts_caption_delivered'))
    delegated = exact(guard, 'await self._send_final_text(event, session_key, text_content, _final_thread_metadata, is_ephemeral_response, _ephemeral_ttl, _record_delivery)')
    if guard.body != [delegated]:
        raise ValueError(error)
    attachments = _exact_deliver_attachments(process)
    ordered([extracted, assigned, metadata, tts_default, guard, attachments])
    # All three stages must be siblings in the response branch.
    branches = [n for n in ast.walk(process) if isinstance(n, ast.If)
                and all(part in n.orelse for part in (extracted, assigned, metadata, tts_default, guard, attachments))]
    if len(branches) != 1 or not _same_expression(branches[0].test, 'not response'):
        raise ValueError(error)
    em = exact(extract, 'media_files, response = self.extract_media(response)')
    fm = _unique_exact_base_node(ast.walk(extract), _is_exact_media_filter_assignment)
    ei = exact(extract, 'images, text_content = self.extract_images(response)')
    strip = exact(extract, 'text_content = _strip_media_directives(text_content).strip()')
    el = exact(extract, 'local_files, text_content = self.extract_local_files(text_content)')
    fl = _unique_exact_base_node(ast.walk(extract), _is_exact_local_filter_assignment)
    recovered = exact(extract, '_recovered = _strip_media_directives(response).strip()')
    restored = exact(extract, 'text_content = _recovered')
    result = exact(extract, 'return _ExtractedResponse(text_content=text_content, images=images, media_files=media_files, local_files=local_files, force_document_attachments=force_document, pre_extract=pre_extract)')
    ordered([em, fm, ei, strip, el, fl, recovered, restored, result])
    adapter = exact(send, 'delivery_adapter = self._final_delivery_adapter(event.source)')
    ledger = exact(send, '_obligation_id = await self._record_delivery_obligation(event, session_key, text_content, delivery_adapter, is_ephemeral_response)')
    final_send = exact(send, 'result = await delivery_adapter._send_with_retry(chat_id=event.source.chat_id, content=text_content, reply_to=_reply_anchor_for_event(event), metadata=metadata)')
    delivered = exact(send, 'record_delivery(result)')
    finalized = exact(send, 'if _obligation_id is not None:\n    await self._finalize_delivery_obligation(_obligation_id, result, event, delivery_adapter)')
    if not all(n in send.body for n in (adapter, ledger, final_send, delivered, finalized)):
        raise ValueError(error)
    ordered([adapter, ledger, final_send, delivered, finalized])
    source = exact(record, 'source = event.source')
    computed = exact(record, 'obligation_id = compute_obligation_id(session_key, str(getattr(event, "message_id", "") or ""), text_content)')
    recorded = exact(record, 'await asyncio.to_thread(record_obligation, obligation_id=obligation_id, session_key=session_key, platform=str(getattr(source.platform, "value", source.platform)), chat_id=source.chat_id, thread_id=getattr(source, "thread_id", None), content=text_content, adapter_profile=getattr(delivery_adapter, "_owner_profile", None))')
    attempting = exact(record, 'await asyncio.to_thread(mark_attempting, obligation_id)')
    returned = exact(record, 'return obligation_id')
    ordered([source, computed, recorded, attempting, returned])
    tries = [n for n in record.body if isinstance(n, ast.Try) and all(x in n.body for x in (source, computed, recorded, attempting, returned))]
    if len(tries) != 1:
        raise ValueError(error)
    exact(finish, 'if getattr(result, "success", False):\n    await asyncio.to_thread(mark_delivered, obligation_id)\n    return')
    exact(finish, 'await asyncio.to_thread(mark_failed, obligation_id, error)')
    return ((guard.lineno - 1, _line_indent(lines, guard.lineno - 1)),
            (final_send.lineno - 1, _line_indent(lines, final_send.lineno - 1)))


def _find_split_decomposed_base_patch_locations(
    tree: ast.Module, lines: list[str], *, owned_ledger_blocks: tuple[str, ...] = (),
) -> tuple[tuple[int, str], tuple[int, str]]:
    """Verify decomposed Hermes after its ledger helper was extracted."""
    error = "could not find safe BasePlatformAdapter contract"
    process = _find_exact_base_process_method(tree)
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BasePlatformAdapter"
    )

    def method(name: Any) -> Any:
        matches = [
            node
            for node in cls.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        ]
        if len(matches) != 1:
            raise ValueError(error)
        return matches[0]

    extract, send, ledger, record, finish = (
        method(name)
        for name in (
            "_extract_response_content",
            "_send_final_text",
            "send_final_ledgered",
            "_record_delivery_obligation",
            "_finalize_delivery_obligation",
        )
    )
    _validate_split_ledger_bracket(ledger, owned_ledger_blocks)
    signatures = (
        (process, ("self", "event", "session_key"), ()),
        (
            extract,
            ("self", "response", "event", "session_key"),
            ("is_ephemeral_response",),
        ),
        (
            send,
            ("self", "event", "session_key", "text_content", "metadata",
             "is_ephemeral_response", "ephemeral_ttl", "record_delivery"),
            (),
        ),
        (
            ledger,
            ("self", "event", "session_key", "text_content", "metadata"),
            ("reply_to", "is_ephemeral_response"),
        ),
        (
            record,
            ("self", "event", "session_key", "text_content", "delivery_adapter",
             "is_ephemeral_response"),
            (),
        ),
        (
            finish,
            ("self", "obligation_id", "result", "event", "delivery_adapter"),
            (),
        ),
    )
    for node, positional, keyword_only in signatures:
        args = node.args
        if (
            tuple(arg.arg for arg in (*args.posonlyargs, *args.args)) != positional
            or tuple(arg.arg for arg in args.kwonlyargs) != keyword_only
            or args.vararg is not None
            or args.kwarg is not None
        ):
            raise ValueError(error)

    def exact(scope: Any, source: Any) -> Any:
        expected = ast.parse(source).body[0]
        return _unique_exact_base_node(
            ast.walk(scope), lambda node: ast.dump(node) == ast.dump(expected)
        )

    def ordered(nodes: Any) -> Any:
        if any(a.lineno >= b.lineno for a, b in zip(nodes, nodes[1:])):
            raise ValueError(error)

    extracted = exact(
        process,
        "extracted = await self._extract_response_content(response, event, session_key, is_ephemeral_response=is_ephemeral_response)",
    )
    assigned = exact(
        process,
        "text_content, media_files = extracted.text_content, extracted.media_files",
    )
    metadata = exact(
        process,
        "_final_thread_metadata = _mark_notify_metadata(_thread_metadata)",
    )
    tts_default = exact(process, "_tts_caption_delivered = False")
    guard = _unique_exact_base_node(
        ast.walk(process),
        lambda node: isinstance(node, ast.If)
        and _same_expression(node.test, "text_content and not _tts_caption_delivered"),
    )
    delegated = exact(
        guard,
        "await self._send_final_text(event, session_key, text_content, _final_thread_metadata, is_ephemeral_response, _ephemeral_ttl, _record_delivery)",
    )
    if guard.body != [delegated]:
        raise ValueError(error)
    attachments = _exact_deliver_attachments(process)
    ordered([extracted, assigned, metadata, tts_default, guard, attachments])
    branches = [
        node
        for node in ast.walk(process)
        if isinstance(node, ast.If)
        and all(
            part in node.orelse
            for part in (extracted, assigned, metadata, tts_default, guard, attachments)
        )
    ]
    if len(branches) != 1 or not _same_expression(branches[0].test, "not response"):
        raise ValueError(error)

    em = exact(extract, "media_files, response = self.extract_media(response)")
    fm = _unique_exact_base_node(ast.walk(extract), _is_exact_media_filter_assignment)
    ei = exact(extract, "images, text_content = self.extract_images(response)")
    strip = exact(extract, "text_content = _strip_media_directives(text_content).strip()")
    el = exact(extract, "local_files, text_content = self.extract_local_files(text_content)")
    fl = _unique_exact_base_node(ast.walk(extract), _is_exact_local_filter_assignment)
    recovered = exact(extract, "_recovered = _strip_media_directives(response).strip()")
    restored = exact(extract, "text_content = _recovered")
    result = exact(
        extract,
        "return _ExtractedResponse(text_content=text_content, images=images, media_files=media_files, local_files=local_files, force_document_attachments=force_document, pre_extract=pre_extract)",
    )
    ordered([em, fm, ei, strip, el, fl, recovered, restored, result])

    delegated_call = exact(
        send,
        "result, delivery_adapter = await self.send_final_ledgered(event, session_key, text_content, metadata, reply_to=_reply_anchor_for_event(event), is_ephemeral_response=is_ephemeral_response)",
    )
    delivered = exact(send, "record_delivery(result)")
    if delegated_call.lineno >= delivered.lineno:
        raise ValueError(error)
    record_source = exact(record, "source = event.source")
    ledger_id = exact(
        record, "_ledger_id = getattr(event, \"ledger_message_id\", None)"
    )
    ledger_fallback = exact(
        record,
        "if _ledger_id is None:\n    _ledger_id = getattr(event, \"message_id\", \"\")",
    )
    computed = _unique_exact_base_node(
        ast.walk(record),
        lambda node: _is_split_compute_obligation_assignment(node),
    )
    recorded = exact(
        record,
        "await asyncio.to_thread(record_obligation, obligation_id=obligation_id, session_key=session_key, platform=str(getattr(source.platform, \"value\", source.platform)), chat_id=source.chat_id, thread_id=getattr(source, \"thread_id\", None), content=text_content, adapter_profile=getattr(delivery_adapter, \"_owner_profile\", None))",
    )
    attempting = exact(record, "await asyncio.to_thread(mark_attempting, obligation_id)")
    returned = exact(record, "return obligation_id")
    ordered([record_source, ledger_id, ledger_fallback, computed, recorded, attempting, returned])
    tries = [
        node
        for node in record.body
        if isinstance(node, ast.Try)
        and all(x in node.body for x in (record_source, ledger_id, ledger_fallback,
                                          computed, recorded, attempting, returned))
    ]
    if len(tries) != 1:
        raise ValueError(error)

    ledger_nodes = list(ast.walk(method("send_final_ledgered")))
    ledger_record = _unique_exact_base_node(ledger_nodes, _is_split_record_obligation_call)
    final_send = _unique_exact_base_node(ledger_nodes, _is_split_final_send_assignment)
    finalized = _unique_exact_base_node(ledger_nodes, _is_split_finalize_obligation_call)
    ledger_return = exact(
        method("send_final_ledgered"), "return result, delivery_adapter"
    )
    ordered([ledger_record, final_send, finalized, ledger_return])
    return (
        (guard.lineno - 1, _line_indent(lines, guard.lineno - 1)),
        (final_send.lineno - 1, _line_indent(lines, final_send.lineno - 1)),
    )
