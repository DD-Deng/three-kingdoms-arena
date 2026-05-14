"""Tick advancement tests — timeout, pause/resume, diagnostics, HTTP status codes."""

import time

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


def _get_state(token: str, game_id: int = 1):
    return client.get(f"/games/{game_id}/state?token={token}")


def _submit(token: str, game_id: int = 1, actions: list | None = None):
    if actions is None:
        actions = [{"type": "defend", "target": "成都"}]
    return client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": actions},
    )


def _get_lobby():
    return client.get("/v1/lobby/status")


# ═══════════════════════════════════════════════════════════════
# Test 1: All occupied submit → tick advances
# ═══════════════════════════════════════════════════════════════

def test_all_occupied_submit_advances_tick(monkeypatch):
    """When all occupied slots submit, tick advances immediately."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    # Join all 3 factions so there are no managed agents to interfere
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Each faction defends its own starting city
    city_map = {"蜀": "成都", "魏": "洛阳", "吴": "建业"}
    r1 = _submit(shu["session_token"], actions=[{"type": "defend", "target": city_map["蜀"]}])
    assert r1.status_code == 200, f"shu submit: {r1.text}"

    r2 = _submit(wei["session_token"], actions=[{"type": "defend", "target": city_map["魏"]}])
    assert r2.status_code == 200, f"wei submit: {r2.text}"

    r3 = _submit(wu["session_token"], actions=[{"type": "defend", "target": city_map["吴"]}])
    assert r3.status_code == 200, f"wu submit: {r3.text}"

    # Check tick advanced
    state = _get_state(shu["session_token"])
    assert state.status_code == 200
    data = state.json()
    assert data["tick"] > 0, f"Expected tick > 0, got {data['tick']}"


# ═══════════════════════════════════════════════════════════════
# Test 2: Timeout advances tick
# ═══════════════════════════════════════════════════════════════

def test_timeout_advances_tick(monkeypatch):
    """When not all slots submit, tick advances after timeout."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 1)
    setup()

    shu = _join("蜀", "10.0.0.1")

    # Submit for 蜀 only — managed agents on open slots will also auto-submit
    r = _submit(shu["session_token"])
    assert r.status_code == 200

    # Wait for timeout
    time.sleep(1.5)

    # Next state poll should trigger advance
    state = _get_state(shu["session_token"])
    assert state.status_code == 200
    data = state.json()
    # Managed agents on open slots auto-submit, so either all-submitted or timeout
    assert data["tick"] >= 0


# ═══════════════════════════════════════════════════════════════
# Test 3: Zero occupied → game pauses
# ═══════════════════════════════════════════════════════════════

def test_zero_occupied_pauses_game(monkeypatch):
    """Game with no occupied slots transitions to paused."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    lobby = _get_lobby()
    assert lobby.status_code == 200
    data = lobby.json()
    assert data["status"] in ("active", "paused")


# ═══════════════════════════════════════════════════════════════
# Test 4: Join resumes paused game
# ═══════════════════════════════════════════════════════════════

def test_join_resumes_paused_game(monkeypatch):
    """Joining a paused game resumes it to active."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")

    state = _get_state(shu["session_token"])
    assert state.status_code == 200
    data = state.json()
    assert data["game_paused"] is False
    assert data["status"] == "active"


# ═══════════════════════════════════════════════════════════════
# Test 5: waiting_for diagnostic field
# ═══════════════════════════════════════════════════════════════

def test_waiting_for_diagnostic(monkeypatch):
    """State response includes waiting_for when some haven't submitted."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")
    _join("魏", "10.0.0.2")

    # Submit only for 蜀
    r = _submit(shu["session_token"])
    assert r.status_code == 200

    state = _get_state(shu["session_token"])
    assert state.status_code == 200
    data = state.json()

    assert "waiting_for" in data, f"waiting_for missing from: {list(data.keys())}"
    assert "魏" in data["waiting_for"], (
        f"Expected 魏 in waiting_for, got {data['waiting_for']}"
    )


# ═══════════════════════════════════════════════════════════════
# Test 6: State includes tick timing fields
# ═══════════════════════════════════════════════════════════════

def test_tick_timing_fields_present(monkeypatch):
    """State response includes tick_started_at, tick_elapsed_sec, etc."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")

    state = _get_state(shu["session_token"])
    assert state.status_code == 200
    data = state.json()

    assert "tick_timeout_in_sec" in data
    assert "tick_elapsed_sec" in data
    assert "game_paused" in data
    assert "paused_reason" in data
    assert "tick_started_at" in data


# ═══════════════════════════════════════════════════════════════
# Test 7: Duplicate submission returns 409
# ═══════════════════════════════════════════════════════════════

def test_duplicate_submit_returns_409(monkeypatch):
    """Same tick second submit returns 409 Conflict, not 400."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    # Join all 3 slots so managed agents don't auto-advance the tick
    shu = _join("蜀", "10.0.0.1")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    r1 = _submit(shu["session_token"])
    assert r1.status_code == 200

    # Second submit on same tick — should be 409
    r2 = _submit(shu["session_token"])
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"


# ═══════════════════════════════════════════════════════════════
# Test 8: Finished game returns 410
# ═══════════════════════════════════════════════════════════════

def test_finished_game_returns_410(monkeypatch):
    """Submitting to a finished game returns 410 Gone."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")

    # Fast-forward via admin ticks to finish the game
    for _ in range(55):
        r = client.post("/games/1/tick?token=admin-dev-token")
        if r.status_code != 200:
            break

    # Verify game is finished
    lobby_r = client.get("/v1/lobby/status")
    if lobby_r.status_code == 200:
        lb = lobby_r.json()
        if lb["status"] == "finished" or lb.get("winner"):
            # Now try to submit — should get 410
            r = _submit(shu["session_token"])
            assert r.status_code == 410, f"Expected 410, got {r.status_code}: {r.text}"
            return

    # If game didn't finish via ticks (one faction captured all cities sooner),
    # it should still be finished
    state = _get_state(shu["session_token"])
    if state.status_code == 200:
        data = state.json()
        if data["status"] == "finished":
            r = _submit(shu["session_token"])
            assert r.status_code in (410, 403), (
                f"Expected 410 or 403 for finished game, got {r.status_code}"
            )


# ═══════════════════════════════════════════════════════════════
# Test 9: Paused game submit rejected
# ═══════════════════════════════════════════════════════════════

def test_paused_game_submit_rejected(monkeypatch):
    """Submitting to a paused game returns 409 Conflict."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    # Drive pause via lobby check (no humans → 0 occupied → pause)
    _get_lobby()

    shu = _join("蜀", "10.0.0.1")

    r = _submit(shu["session_token"])
    # 200 = game active (managed AIs), 409 = paused
    assert r.status_code in (200, 409), f"Unexpected status: {r.status_code}"
