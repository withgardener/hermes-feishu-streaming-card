from __future__ import annotations

import asyncio
from types import SimpleNamespace

from hermes_feishu_card.flush import FlushController


def test_flush_controller_reports_real_coalesced_backlog_depth():
    async def scenario():
        metrics = SimpleNamespace(
            update_scheduled=0,
            update_coalesced=0,
            update_queue_peak=0,
            terminal_drains=0,
            terminal_drain_latency_ms=0,
            terminal_drain_timeouts=0,
        )
        controller = FlushController(interval_seconds=0, metrics=metrics)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def render():
            entered.set()
            await release.wait()
            return True

        task = controller.schedule(render)
        await entered.wait()
        controller.schedule(render)
        controller.schedule(render)
        controller.schedule(render)

        assert controller.snapshot()["pending_count"] == 3
        assert metrics.update_scheduled == 4
        assert metrics.update_coalesced == 3
        assert metrics.update_queue_peak == 3
        release.set()
        await task

    asyncio.run(scenario())
