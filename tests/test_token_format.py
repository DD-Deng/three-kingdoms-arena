"""Token format and TTL tests — P1-5."""

import re
import time

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel, Session, select
from app.database import engine
from app.models import Agent

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


def _state(token: str, game_id: int = 1):
    return client.get(f"/games/{game_id}/state?token={token}")


# ═══════════════════════════════════════════════════════════════
# Test 1: New token format matches ^tk_[a-f0-9]{32}$
# ═══════════════════════════════════════════════════════════════

def test_token_format_shell_friendly(monkeypatch):
    """Session tokens use tk_ prefix + 32 hex chars."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    token = shu["session_token"]
    assert re.match(r"^tk_[a-f0-9]{32}$", token), f"Bad format: {token}"
    assert len(token) == 35


# ═══════════════════════════════════════════════════════════════
# Test 2: State API returns token expiry fields
# ═══════════════════════════════════════════════════════════════

def test_state_returns_token_expiry(monkeypatch):
    """State API includes your_token_expires_at and your_token_expires_in_sec."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")

    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state failed: {s.text}"
    data = s.json()

    assert "your_token_expires_at" in data, \
        f"your_token_expires_at missing from: {list(data.keys())}"
    assert "your_token_expires_in_sec" in data, \
        f"your_token_expires_in_sec missing from: {list(data.keys())}"

    expires_at = data["your_token_expires_at"]
    expires_in = data["your_token_expires_in_sec"]

    assert expires_at is not None, "your_token_expires_at should not be None"
    assert expires_in is not None, "your_token_expires_in_sec should not be None"
    assert "T" in expires_at, f"Should be ISO timestamp: {expires_at}"
    # Token should expire in ~2 hours (7200 sec)
    assert 7000 < expires_in <= 7200, \
        f"Expected ~7200, got {expires_in}"


# ═══════════════════════════════════════════════════════════════
# Test 3: Session TTL is 2 hours (7200s)
# ═══════════════════════════════════════════════════════════════

def test_session_ttl_2_hours():
    """SESSION_MAX_AGE_SEC is set to 7200 (2 hours)."""
    from app.lobby import SESSION_MAX_AGE_SEC
    assert SESSION_MAX_AGE_SEC == 7200, f"Expected 7200, got {SESSION_MAX_AGE_SEC}"


# ═══════════════════════════════════════════════════════════════
# Test 4: Reconnect grace is 10 minutes (600s)
# ═══════════════════════════════════════════════════════════════

def test_reconnect_grace_10_minutes():
    """RECONNECT_GRACE_SEC is set to 600 (10 minutes)."""
    from app.lobby import RECONNECT_GRACE_SEC
    assert RECONNECT_GRACE_SEC == 600, f"Expected 600, got {RECONNECT_GRACE_SEC}"


# ═══════════════════════════════════════════════════════════════
# Test 5: Agent token also uses new format
# ═══════════════════════════════════════════════════════════════

def test_agent_token_new_format(monkeypatch):
    """Agent table token field uses the new tk_ format."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀")

    with Session(engine) as session:
        agents = session.exec(
            select(Agent).where(Agent.game_id == 1, Agent.is_active == True)
        ).all()
        for a in agents:
            assert re.match(r"^tk_[a-f0-9]{32}$", a.token), \
                f"Agent token bad format: {a.token}"
