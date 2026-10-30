from __future__ import annotations


def _deliver_result(job: dict, content: str, adapters=None, loop=None):
    adapter = (adapters or {}).get(job.get("platform"))
    if adapter is None:
        return None
    return adapter.send(job.get("target"), content)
