"""Single authenticated request to the original Hermes interaction resolver.

No session mutation, retry, claim or permission decision lives here. The caller
must verify the current owner before the request and again before applying its
result. Only an exact, timely resolver acknowledgement counts as resolved.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import time
from typing import Any, cast

from aiohttp import ClientSession, ClientTimeout

from .event_auth import sign_runtime_interaction_request
from .runtime_interaction_transport import RUNTIME_INTERACTION_PATH


RUNTIME_INTERACTION_CALLBACK_TIMEOUT_SECONDS = 2.0
MAX_RUNTIME_INTERACTION_RESPONSE_BYTES = 512


@dataclass(frozen=True)
class ResolutionOutcome:
    reason: str

    @property
    def resolved(self) -> bool:
        return self.reason == "resolved"


async def resolve_interaction(
    secret: object,
    descriptor: dict[str, Any],
    choice: str,
) -> ResolutionOutcome:
    if type(secret) is not bytes or len(secret) != 32:
        return ResolutionOutcome("secret_unavailable")
    if (
        type(descriptor) is not dict
        or set(descriptor)
        != {
            "protocol",
            "runtime_id",
            "resolve_url",
            "interaction_key",
            "token",
            "expires_at",
        }
        or type(choice) is not str
        or not choice.strip()
    ):
        return ResolutionOutcome("invalid_descriptor")
    expires_at = cast(float, descriptor.get("expires_at"))
    if type(expires_at) not in (int, float) or time.time() >= expires_at:
        return ResolutionOutcome("expired_before_request")
    body_value = {
        "protocol": descriptor["protocol"],
        "runtime_id": descriptor["runtime_id"],
        "interaction_key": descriptor["interaction_key"],
        "token": descriptor["token"],
        "choice": choice,
        "expires_at": expires_at,
    }
    try:
        body = json.dumps(
            body_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        headers.update(
            sign_runtime_interaction_request(
                secret,
                RUNTIME_INTERACTION_PATH,
                body,
            )
        )
        timeout = ClientTimeout(total=RUNTIME_INTERACTION_CALLBACK_TIMEOUT_SECONDS)
        async with ClientSession(
            trust_env=False,
            timeout=timeout,
            auto_decompress=False,
        ) as client:
            async with client.post(
                descriptor["resolve_url"],
                data=body,
                headers=headers,
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return ResolutionOutcome(f"http_{response.status}")
                lengths = response.headers.getall("Content-Length", [])
                if len(lengths) > 1:
                    return ResolutionOutcome("invalid_response")
                if lengths:
                    try:
                        declared = int(lengths[0])
                    except (TypeError, ValueError):
                        return ResolutionOutcome("invalid_response")
                    if not 0 <= declared <= MAX_RUNTIME_INTERACTION_RESPONSE_BYTES:
                        return ResolutionOutcome("invalid_response")
                # read(n) may return a valid JSON prefix before the response
                # ends. Wait for EOF, or one byte beyond the bounded budget,
                # under the existing whole-request timeout.
                try:
                    raw = await response.content.readexactly(
                        MAX_RUNTIME_INTERACTION_RESPONSE_BYTES + 1
                    )
                except asyncio.IncompleteReadError as exc:
                    raw = exc.partial
    except asyncio.CancelledError:
        raise
    except (asyncio.TimeoutError, TimeoutError):
        return ResolutionOutcome("timeout")
    except Exception:
        return ResolutionOutcome("transport_error")
    if len(raw) > MAX_RUNTIME_INTERACTION_RESPONSE_BYTES or time.time() >= expires_at:
        return ResolutionOutcome(
            "invalid_response"
            if len(raw) > MAX_RUNTIME_INTERACTION_RESPONSE_BYTES
            else "expired_after_request"
        )
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ResolutionOutcome("invalid_response")
    resolved = (
        type(result) is dict
        and all(type(key) is str for key in result)
        and set(result) == {"ok", "status"}
        and result["ok"] is True
        and type(result["status"]) is str
        and result["status"] == "resolved"
    )
    if not resolved:
        return ResolutionOutcome("invalid_response")
    return ResolutionOutcome("resolved")

