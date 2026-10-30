"""Real HTTP accepted events expose bounded timing totals without extra delivery."""
import asyncio
import json
import time
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from hermes_feishu_card import server, session as session_module
from hermes_feishu_card.support_report import build_support_report


class Capture:
    def __init__(self):
        self.sent, self.updated = [], []

    async def send_card(self, chat_id, card, **kwargs):
        self.sent.append(card)
        return "fixture-card-" + str(len(self.sent))

    async def update_card_message(self, message_id, card):
        self.updated.append((message_id, card))


def event(kind, sequence, turn, data=None):
    return dict(schema_version="1", event=kind, sequence=sequence, conversation_id="fixture-chat", message_id=turn, chat_id="fixture-chat", platform="feishu", created_at=time.time(), data=data or {})


async def test_health_aggregates_only_retained_observed_turns_and_never_adds_patch(tmp_path, monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(session_module, "time", SimpleNamespace(time=time.time, monotonic=lambda: clock.now))
    monkeypatch.setattr(server, "CARD_ANIMATION_MAX_UPDATES", 0)
    capture = Capture()
    app = server.create_app(capture, card_config={"flush_interval_ms": 0}, session_store_directory=tmp_path)
    async with TestClient(TestServer(app)) as http:
        for now, kind, sequence, turn, data in [
            (100, "message.started", 0, "PRIVATE_TURN_ONE", {}),
            (101, "answer.delta", 1, "PRIVATE_TURN_ONE", {"text": "FIRST", "model": "PRIVATE_MODEL_ONE"}),
            (105, "message.completed", 2, "PRIVATE_TURN_ONE", {"answer": "FINAL", "model": "PRIVATE_MODEL_TWO", "tokens": {"output_tokens": 9000}}),
            (200, "answer.delta", 0, "PRIVATE_ORPHAN", {"text": "NO_START"}),
            (210, "message.completed", 1, "PRIVATE_ORPHAN", {"answer": "FINAL_WITHOUT_START"}),
            (300, "message.started", 0, "PRIVATE_TURN_THREE", {}),
            (302, "answer.delta", 1, "PRIVATE_TURN_THREE", {"text": "ONGOING"}),
        ]:
            clock.now = now
            assert (await http.post("/events", json=event(kind, sequence, turn, data))).status == 200
        for _ in range(100):
            if len(capture.updated) >= 3:
                break
            await asyncio.sleep(0.01)
        assert capture.updated
        before = (len(capture.sent), len(capture.updated))
        samples = [(await (await http.get("/health")).json())["timing"] for _ in range(3)]
        assert samples == [samples[0]] * 3
        timing = samples[0]
        assert timing == {
            "scope": "sidecar_accepted_events", "window": "retained_session_memory", "clock": "monotonic",
            "started_samples": 2, "first_answer_samples": 2, "first_answer_total_ms": 3000,
            "completed_samples": 1, "observed_turn_total_ms": 5000,
            "token_rate_status": "unavailable", "token_rate_reason": "model_invocation_scope_missing",
        }
        assert before == (len(capture.sent), len(capture.updated))
        assert "PRIVATE" not in json.dumps(timing)
        payload_text = json.dumps(capture.sent + [card for _, card in capture.updated])
        assert "first_answer_ms" not in payload_text and "token_rate" not in payload_text
        assert build_support_report({"runtime": {"timing": timing}})["diagnostics"]["runtime"]["timing"] == timing
        app[server.SESSIONS_KEY].pop("PRIVATE_TURN_ONE")
        retained = (await (await http.get("/health")).json())["timing"]
        assert retained["started_samples"] == 1
        assert retained["completed_samples"] == 0
        assert retained["first_answer_total_ms"] == 2000
