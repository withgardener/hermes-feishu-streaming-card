from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

import pytest
from aiohttp import StreamReader, web

from hermes_feishu_card import interaction_resolver as resolver


SECRET = b'x' * 32
ACK = b'{"ok":true,"status":"resolved"}'


def descriptor(url, *, expires_at=None):
    return dict(protocol='hfc-runtime-interaction-v1', runtime_id='runtime-test',
                resolve_url=url, interaction_key='interaction-test', token='token-test',
                expires_at=time.time() + 60 if expires_at is None else expires_at)


@asynccontextmanager
async def endpoint(handler):
    app = web.Application()
    app.router.add_post('/resolve', handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f'http://127.0.0.1:{port}/resolve'
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('tail', [b' ', b'garbage', b' ' * 513], ids=['valid-suffix', 'invalid-suffix', 'oversize-suffix'])
async def test_requires_complete_chunked_response_before_accepting_ack(monkeypatch, tail):
    release = asyncio.Event()
    prefix_consumed = asyncio.Event()
    original_read = StreamReader.read

    async def observed_read(self, n=-1):
        value = await original_read(self, n)
        if value == ACK:
            prefix_consumed.set()
        return value

    monkeypatch.setattr(StreamReader, 'read', observed_read)

    async def handler(request):
        await request.read()
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(ACK)
        await release.wait()
        try:
            await response.write(tail)
            await response.write_eof()
        except ConnectionResetError:
            pass
        return response

    async with endpoint(handler) as url:
        task = asyncio.create_task(resolver.resolve_interaction(SECRET, descriptor(url), 'yes'))
        try:
            await asyncio.wait_for(prefix_consumed.wait(), 2)
            assert not task.done(), 'accepted JSON prefix before response EOF'
            release.set()
            result = await asyncio.wait_for(task, 2)
            assert result.reason == ('resolved' if tail == b' ' else 'invalid_response')
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('body,status,reason', [
    (ACK, 200, 'resolved'),
    (b'{"ok":1,"status":"resolved"}', 200, 'invalid_response'),
    (b'{"ok":true,"status":"resolved","extra":1}', 200, 'invalid_response'),
    (b'null', 200, 'invalid_response'),
    (b'\xff', 200, 'invalid_response'),
    (b'x' * 513, 200, 'invalid_response'),
    (ACK, 503, 'http_503'),
    (ACK, 302, 'http_302'),
])
async def test_exact_response_and_single_request(body, status, reason):
    requests = []

    async def handler(request):
        requests.append((await request.read(), dict(request.headers)))
        return web.Response(body=body, status=status)

    async with endpoint(handler) as url:
        result = await resolver.resolve_interaction(SECRET, descriptor(url), '确定')
    assert result.reason == reason
    assert len(requests) == 1
    assert json.loads(requests[0][0])['choice'] == '确定'
    assert b'\\u786e' not in requests[0][0]


@pytest.mark.asyncio
async def test_cancel_propagates_and_does_not_retry():
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def handler(request):
        nonlocal count
        count += 1
        entered.set()
        await release.wait()
        return web.Response(body=ACK)

    async with endpoint(handler) as url:
        task = asyncio.create_task(resolver.resolve_interaction(SECRET, descriptor(url), 'yes'))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
    assert count == 1


@pytest.mark.asyncio
async def test_expiry_during_request_rejects_exact_ack(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resolver.time, 'time', lambda: clock[0])

    async def handler(request):
        clock[0] = 101.0
        return web.Response(body=ACK)

    async with endpoint(handler) as url:
        result = await resolver.resolve_interaction(SECRET, descriptor(url, expires_at=101.0), 'yes')
    assert result.reason == 'expired_after_request'


@pytest.mark.asyncio
async def test_invalid_inputs_never_construct_client(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('invalid input opened an HTTP client')

    monkeypatch.setattr(resolver, 'ClientSession', forbidden)
    valid = descriptor('http://127.0.0.1:1/resolve')
    assert (await resolver.resolve_interaction(b'bad', valid, 'yes')).reason == 'secret_unavailable'
    assert (await resolver.resolve_interaction(SECRET, {}, 'yes')).reason == 'invalid_descriptor'
    assert (await resolver.resolve_interaction(SECRET, valid, ' ')).reason == 'invalid_descriptor'
    assert (await resolver.resolve_interaction(SECRET, descriptor(valid['resolve_url'], expires_at=0), 'yes')).reason == 'expired_before_request'


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_not_retried(monkeypatch):
    release = asyncio.Event()
    count = 0
    monkeypatch.setattr(resolver, 'RUNTIME_INTERACTION_CALLBACK_TIMEOUT_SECONDS', 0.02)

    async def handler(request):
        nonlocal count
        count += 1
        await release.wait()
        return web.Response(body=ACK)

    async with endpoint(handler) as url:
        try:
            result = await asyncio.wait_for(resolver.resolve_interaction(SECRET, descriptor(url), 'yes'), 2)
            assert result.reason == 'timeout'
        finally:
            release.set()
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True], ids=['teardown-error', 'teardown-cancel'])
async def test_wrapper_counts_teardown_failure_once_and_propagates_cancel(monkeypatch, cancel):
    from hermes_feishu_card import server
    from types import SimpleNamespace

    class Response:
        status = 503

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            if cancel:
                raise asyncio.CancelledError
            raise RuntimeError('synthetic teardown failure')

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
            assert kwargs['auto_decompress'] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            assert kwargs['allow_redirects'] is False
            return Response()

    monkeypatch.setattr(resolver, 'ClientSession', Client)
    metrics = SimpleNamespace(runtime_interaction_callback_attempts=0,
                              runtime_interaction_callback_failures=0,
                              runtime_interaction_callback_successes=0)
    app = {server.METRICS_KEY: metrics, server.DIAGNOSTICS_KEY: {},
           server.OPERATIONS_TRANSPORT_ROOT_KEY: SECRET}
    call = server._resolve_runtime_interaction_callback(app, descriptor('http://127.0.0.1:1/resolve'), 'yes')
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await call
    else:
        assert await call is False
    assert metrics.runtime_interaction_callback_attempts == 1
    assert metrics.runtime_interaction_callback_failures == 1
    assert metrics.runtime_interaction_callback_successes == 0
    assert app[server.DIAGNOSTICS_KEY]['last_runtime_interaction_callback'] == ('cancelled' if cancel else 'transport_error')
