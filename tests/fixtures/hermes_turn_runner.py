class TurnContext:
    pass


class TurnRunner:
    def __init__(self, runner, ctx):
        self._runner = runner
        self._ctx = ctx

    def progress_callback(
        self,
        event_type: str,
        tool_name: str = None,
        preview: str = None,
        args: dict = None,
        **kwargs,
    ):
        ctx = self._ctx
        if not ctx._run_still_current():
            return
        ctx.progress_queue.put((event_type, tool_name, preview))

    def _status_callback_sync(self, event_type: str, message: str) -> None:
        ctx = self._ctx
        if not ctx._status_adapter or not ctx._run_still_current():
            return
        ctx.status_queue.put((event_type, message))

    def run_sync(self):
        ctx = self._ctx
        agent = self._runner.agent
        stream_consumer = self._runner.stream_consumer

        def _stream_delta_cb(text: str) -> None:
            if ctx._run_still_current():
                stream_consumer.on_delta(text)

        def _interim_assistant_cb(
            text: str, *, already_streamed: bool = False
        ) -> None:
            if text and not already_streamed and ctx._run_still_current():
                stream_consumer.on_commentary(text)

        agent.tool_progress_callback = ctx.progress_callback
        agent.tool_start_callback = self._runner.voice_ack_callback
        agent.stream_delta_callback = _stream_delta_cb
        agent.interim_assistant_callback = _interim_assistant_cb
        agent.status_callback = ctx._status_callback_sync

        def _clarify_callback_sync(question: str, choices):
            if not ctx._status_adapter:
                return ""
            return ctx.wait_for_clarify(question, choices)

        agent.clarify_callback = _clarify_callback_sync
        _approval_session_key = ctx.session_key or ""

        def _approval_notify_sync(approval_data: dict) -> None:
            ctx.send_approval(_approval_session_key, approval_data)

        agent.approval_callback = _approval_notify_sync
        return agent


class GatewayRunner:
    async def _handle_message_with_agent(
        self, event, source, _quick_key, run_generation
    ):
        response = "ok"
        agent_result = {"model": "m"}
        _response_time = 1.0
        await self.hooks.emit("agent:end", {"response": response})
        return response

    async def _run_agent(self, source, event_message_id=None):
        turn_ctx = TurnContext()
        turn_ctx.source = source
        turn_ctx.event_message_id = event_message_id
        turn_ctx.session_key = "session"
        turn_ctx._loop_for_step = self.loop
        turn_ctx._run_still_current = self._run_still_current
        turn_ctx._status_chat_id = source.chat_id
        turn_ctx._status_adapter = self._adapter_for_source(source)
        turn_ctx.progress_queue = self.progress_queue
        turn_ctx.status_queue = self.status_queue
        turn_ctx.agent_holder = [None]
        turn_runner = TurnRunner(self, turn_ctx)
        turn_ctx.progress_callback = turn_runner.progress_callback
        turn_ctx._status_callback_sync = turn_runner._status_callback_sync
        return turn_runner.run_sync()


def _reply_anchor_for_event(event):
    return getattr(event, "reply_to_message_id", None)


def _deliver_media_from_response(response):
    return extract_media(response)


def _deliver_result(job: dict, content: str, adapters=None, loop=None):
    return None
