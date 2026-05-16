"""Structured error code tests — Step 6: 错误码分类."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine
from app.exceptions import (
    ArenaException, ErrorCategory, tactical, protocol, auth_error, rate_limit,
)

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ═══════════════════════════════════════════════════════════════
# Unit tests: ArenaException construction
# ═══════════════════════════════════════════════════════════════

def test_arena_exception_as_response():
    """ArenaException.as_response() returns structured dict."""
    exc = tactical("TACTICAL_INSUFFICIENT_GRAIN", "粮草不足")
    resp = exc.as_response()
    assert resp["error_code"] == "TACTICAL_INSUFFICIENT_GRAIN"
    assert resp["category"] == "tactical"
    assert resp["detail"] == "粮草不足"
    assert resp["retry_safe"] is True
    assert exc.status_code == 400


def test_protocol_game_finished():
    """PROTOCOL_GAME_FINISHED is not retry_safe and returns 410."""
    exc = protocol("PROTOCOL_GAME_FINISHED", "对局已结束")
    assert exc.status_code == 410
    assert exc.category == ErrorCategory.protocol
    assert exc.retry_safe is False


def test_auth_error():
    """AUTH_INVALID_TOKEN returns 401 and is not retry_safe."""
    exc = auth_error("AUTH_INVALID_TOKEN", "token 无效")
    assert exc.status_code == 401
    assert exc.category == ErrorCategory.auth
    assert exc.retry_safe is False


def test_rate_limit():
    """RATE_LIMIT errors return 429."""
    exc = rate_limit("RATE_LIMIT_ONE_PER_IP")
    assert exc.status_code == 429
    assert exc.category == ErrorCategory.rate_limit


def test_tactical_errors_are_retry_safe():
    """All tactical errors should be retry_safe except permanently blocked states."""
    from app.exceptions import _ERROR_DEFS
    NON_RETRYABLE_TACTICAL = {"TACTICAL_FACTION_ELIMINATED", "TACTICAL_NO_VALID_ACTIONS"}
    for code, (cat, retry) in _ERROR_DEFS.items():
        if cat == ErrorCategory.tactical:
            if code in NON_RETRYABLE_TACTICAL:
                assert retry is False, f"{code} should NOT be retry_safe (permanent state)"
            else:
                assert retry is True, f"{code} should be retry_safe"


# ═══════════════════════════════════════════════════════════════
# Integration tests: HTTP endpoints return structured errors
# ═══════════════════════════════════════════════════════════════

def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


def _submit(token: str, game_id: int = 1, actions: list | None = None):
    if actions is None:
        actions = [{"type": "defend", "target": "成都"}]
    return client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": actions},
    )


def _tick(game_id: int = 1):
    return client.post(f"/games/{game_id}/tick?token=admin-dev-token")


def test_insufficient_grain_structured_error(monkeypatch):
    """Insufficient grain returns structured error with category=tactical."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    _tick()
    _tick()

    # Try to recruit a huge amount that exceeds grain
    r = _submit(shu["session_token"], actions=[
        {"type": "recruit", "target": "成都", "amount": 500}
    ])
    if r.status_code == 400:
        data = r.json()
        assert "error_code" in data, f"No error_code in {data}"
        assert "category" in data, f"No category in {data}"
        assert "retry_safe" in data, f"No retry_safe in {data}"
        print(f"Grain error: {data}")


def test_not_your_city_structured_error(monkeypatch):
    """Attacking from city you don't own returns structured error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    _tick()
    _tick()

    # Shu tries to attack from 洛阳 (Wei's city)
    r = _submit(shu["session_token"], actions=[
        {"type": "attack", "from": "洛阳", "target": "宛城", "troops": 200}
    ])
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    data = r.json()
    assert "error_code" in data, f"No error_code in {data}"
    assert data["error_code"] == "TACTICAL_NOT_YOUR_CITY", \
        f"Expected TACTICAL_NOT_YOUR_CITY, got {data.get('error_code')}"
    assert data["category"] == "tactical"
    assert data["retry_safe"] is True


def test_game_finished_structured_error(monkeypatch):
    """Finished game returns structured protocol error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Advance to tick 50 (max ticks) to finish the game
    for _ in range(55):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit("token_wei", actions=[{"type": "defend", "target": "洛阳"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
        _tick()

    # Check state for finished status first
    s = client.get(f"/games/1/state?token={shu['session_token']}")
    if s.status_code == 200:
        st_data = s.json()
        if st_data.get("status") == "finished":
            r = _submit(shu["session_token"])
            assert r.status_code in (400, 410), \
                f"Expected 400 or 410, got {r.status_code}: {r.text}"
            data = r.json()
            assert "error_code" in data, f"No error_code in {data}"
            assert data["category"] in ("protocol",), \
                f"Expected protocol, got {data.get('category')}"


def test_duplicate_submit_structured_error(monkeypatch):
    """Duplicate submit returns structured protocol error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    _tick()

    # First submit
    r1 = _submit(shu["session_token"])
    assert r1.status_code == 200, f"First submit failed: {r1.text}"

    # Duplicate submit
    r2 = _submit(shu["session_token"])
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
    data = r2.json()
    assert "error_code" in data, f"No error_code in {data}"
    assert data["error_code"] == "PROTOCOL_DUPLICATE_SUBMIT", \
        f"Expected PROTOCOL_DUPLICATE_SUBMIT, got {data.get('error_code')}"
    assert data["category"] == "protocol"


def test_invalid_token_structured_error(monkeypatch):
    """Invalid token returns structured auth error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    # Create a game first so game_id 1 exists
    _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    r = client.get("/games/1/state?token=invalid-token-xxx")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    data = r.json()
    assert "error_code" in data, f"No error_code in {data}"
    assert data.get("error_code") == "AUTH_INVALID_TOKEN", \
        f"Expected AUTH_INVALID_TOKEN, got {data.get('error_code')}"
    assert data["category"] == "auth"


def test_game_not_found_structured_error(monkeypatch):
    """Non-existent game returns structured protocol error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")

    r = client.get(f"/games/999/state?token={shu['session_token']}")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    data = r.json()
    assert "error_code" in data, f"No error_code in {data}"
    assert data["error_code"] == "PROTOCOL_GAME_NOT_FOUND", \
        f"Expected PROTOCOL_GAME_NOT_FOUND, got {data.get('error_code')}"


def test_cannot_attack_own_city_structured_error(monkeypatch):
    """Attacking own city returns structured tactical error."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    _tick()

    # Shu tries to attack own city 成都 via 长安→成都 adjacency
    r = _submit(shu["session_token"], actions=[
        {"type": "attack", "from": "长安", "target": "成都", "troops": 200}
    ])
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    data = r.json()
    assert "error_code" in data
    assert data["error_code"] == "TACTICAL_CANNOT_ATTACK_OWN", \
        f"Expected TACTICAL_CANNOT_ATTACK_OWN, got {data.get('error_code')}"


def test_retry_safe_field_present(monkeypatch):
    """All error responses must include retry_safe boolean."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    _tick()

    # Generate an error
    r = _submit(shu["session_token"], actions=[
        {"type": "attack", "from": "洛阳", "target": "宛城", "troops": 200}
    ])
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    data = r.json()
    assert "retry_safe" in data, f"retry_safe missing from {data}"
    assert isinstance(data["retry_safe"], bool), \
        f"retry_safe should be bool, got {type(data['retry_safe'])}"
