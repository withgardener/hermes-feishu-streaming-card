class GatewayNotificationsMixin:
    async def _deliver_platform_notice(self, source, content):
        adapter = self._adapter_for_source(source)
        reply_to = self._reply_anchor_for_event(source)
        return await adapter.send(chat_id=source.chat_id, content=content, reply_to=reply_to)

    async def _deliver_media_from_response(self, response, event, session_key):
        return await self._adapter_for_source(event).extract_media(response)
