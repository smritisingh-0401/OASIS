"""Logs and traces never contain message text or session IDs (rules P1, P2)."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from oasis.api.app import create_app
from oasis.llm.fake import FakeLLM
from oasis.settings import Settings

MARKER = "MARKER-7731 zebra lantern"


@pytest.mark.parametrize("llm", [FakeLLM(), FakeLLM(fail="down")])
def test_logs_hold_no_message_text_or_session_id(
    settings: Settings, caplog: pytest.LogCaptureFixture, llm: FakeLLM
) -> None:
    caplog.set_level(logging.DEBUG)
    with TestClient(create_app(settings, llm=llm)) as c:
        token = c.post("/session").json()["session_id"]
        c.post(
            "/chat",
            json={"message": MARKER, "client_ts": "2026-10-07T10:00:00Z"},
            headers={"X-OASIS-Session": token},
        )
        c.post(
            "/chat",
            json={"message": MARKER * 100, "client_ts": "bad"},
            headers={"X-OASIS-Session": token},
        )

    assert MARKER not in caplog.text
    assert "zebra" not in caplog.text
    assert token not in caplog.text

    traces = [r for r in caplog.records if r.name == "oasis.turn"]
    assert len(traces) == 1
    trace = json.loads(traces[0].getMessage())
    assert {"turn_id", "stages", "safety", "plan_mode", "llm_attempts"} <= trace.keys()
    assert trace["stages"][0]["name"] == "safety"
