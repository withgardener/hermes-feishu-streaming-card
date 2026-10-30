"""Bounded observer workers against a real, gated loopback HTTP endpoint."""
from __future__ import annotations

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from urllib.request import Request, urlopen

import pytest

from hermes_feishu_card.turn_events import TurnEventCoordinator


@pytest.mark.parametrize("session_count", [1, 5, 20])
@pytest.mark.parametrize("outcome", ["normal", "http_failure", "close_blocked"])
def test_observer_http_saturation_and_three_round_worker_reclamation(
    session_count, outcome, record_property,
):
    """Bound queue acceptance while IO is blocked, then reap three real waves.

    Failure is a real HTTP 503. Interruption closes coordinators with IO still
    blocked; accepted work may drain after release, but new work must be refused.
    This is a finite scheduler/resource test, not a long-lived memory soak.
    """
    baseline_workers = {thread for thread in threading.enumerate() if thread.name == "hfc-turn-observer"}
    round_records = []
    for round_number in range(3):
        release = threading.Event()
        lock = threading.Lock()
        entered = set()
        received = []
        coordinators = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with lock:
                    entered.add(body["turn"])
                if not release.wait(10):
                    self.send_error(504)
                    return
                with lock:
                    received.append(body)
                self.send_response(503 if outcome == "http_failure" else 200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_args):
                pass

        class Server(ThreadingHTTPServer):
            request_queue_size = 128
            daemon_threads = True

        server = Server(("127.0.0.1", 0), Handler)
        serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), name="hfc-test-http")
        serving.start()
        accepted = Counter()
        try:
            for index in range(session_count):
                turn = f"load-{round_number}-{index}"

                def deliver(event, turn=turn):
                    body = json.dumps({"turn": turn, "sequence": event.sequence}).encode()
                    request = Request(f"http://127.0.0.1:{server.server_port}/", data=body,
                                      headers={"Content-Type": "application/json"})
                    with urlopen(request, timeout=10) as response:
                        response.read()

                coordinator = TurnEventCoordinator(turn, max_pending=8, deliver=deliver)
                coordinators.append(coordinator)
                assert coordinator.submit_observer({"event": "answer.delta"}, producer="plugin")
                accepted[turn] += 1
            deadline = time.monotonic() + 5
            while len(entered) < session_count and time.monotonic() < deadline:
                time.sleep(0.005)
            assert len(entered) == session_count
            for coordinator in coordinators:
                for _ in range(200):
                    accepted[coordinator.turn_id] += coordinator.submit_observer(
                        {"event": "answer.delta"}, producer="plugin"
                    )
                # One request is in-flight; precisely eight slots remain.
                assert accepted[coordinator.turn_id] == 9
                coordinator.close_terminal_barrier()
                coordinator.drain_before_terminal(0.001)
                terminal_sequence = coordinator.next_terminal_sequence()
                assert terminal_sequence > 8
                assert not coordinator.submit_observer({"event": "answer.delta"}, producer="plugin")
            live = {thread for thread in threading.enumerate() if thread.name == "hfc-turn-observer"}
            assert len(live - baseline_workers) == session_count
            close_started = time.monotonic()
            if outcome == "close_blocked":
                for coordinator in coordinators:
                    coordinator.close()
                assert time.monotonic() - close_started < session_count * 0.25 + 0.5
            release.set()
            for coordinator in coordinators:
                coordinator.drain_before_terminal(5)
                coordinator.close()
            deadline = time.monotonic() + 5
            while any(coordinator._worker.is_alive() for coordinator in coordinators) and time.monotonic() < deadline:
                time.sleep(0.005)
            assert all(not coordinator._worker.is_alive() for coordinator in coordinators)
            counts = Counter(item["turn"] for item in received)
            assert counts == accepted  # no retries, duplicates, loss, or route bleed
            for turn in accepted:
                assert [item["sequence"] for item in received if item["turn"] == turn] == list(range(9))
            assert {thread for thread in threading.enumerate() if thread.name == "hfc-turn-observer"} <= baseline_workers
            round_records.append({"round": round_number, "workers": session_count,
                                  "offered_per_turn": 201, "accepted_per_turn": 9,
                                  "http_requests": len(received), "workers_remaining": 0})
        finally:
            release.set()
            for coordinator in coordinators:
                coordinator.close()
                coordinator._worker.join(timeout=5)
            server.shutdown()
            server.server_close()
            serving.join(timeout=5)
            assert not serving.is_alive()
    record_property("rounds", json.dumps(round_records))
