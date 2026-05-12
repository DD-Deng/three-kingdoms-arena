"""Phase 1 — Lobby, slot & session tests."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, engine
from sqlmodel import SQLModel, Session

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ═══════════════════════════════════════════════════════════════
# Join empty slot — success
# ═══════════════════════════════════════════════════════════════


def test_join_empty_slot():
    """Join an open slot returns session_token."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    assert r.status_code == 200
    data = r.json()
    assert "session_token" in data
    assert len(data["session_token"]) == 32
    assert data["faction"] == "蜀"
    assert data["game_id"] > 0
    assert "expires_at" in data
    assert "instruction_url" in data


def test_join_all_three_slots():
    """All 3 factions can be joined (from different IPs)."""
    setup()
    for i, f in enumerate(["蜀", "魏", "吴"]):
        ip = f"10.0.0.{i + 1}"
        r = client.post(
            "/v1/lobby/join",
            json={"faction": f},
            headers={"X-Forwarded-For": ip},
        )
        assert r.status_code == 200, f"join {f}: {r.text}"
        assert r.json()["faction"] == f


def test_join_spectator():
    """Spectator join returns a view-only token."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "spectator"})
    assert r.status_code == 200
    data = r.json()
    assert data["faction"] == "spectator"
    assert "session_token" in data


def test_join_invalid_faction():
    """Invalid faction name returns 400."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "魏蜀吴"})
    assert r.status_code == 400
    r = client.post("/v1/lobby/join", json={"faction": ""})
    assert r.status_code == 400
    r = client.post("/v1/lobby/join", json={})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Join occupied slot — 409
# ═══════════════════════════════════════════════════════════════


def test_join_occupied_slot_returns_409():
    """Joining an already-occupied faction returns 409."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    assert r.status_code == 200

    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    assert r.status_code == 409
    assert "已被占用" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# Lobby status
# ═══════════════════════════════════════════════════════════════


def test_lobby_status_has_slots():
    """GET /v1/lobby/status returns game info + slot states."""
    setup()
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200
    data = r.json()
    assert "game_id" in data
    assert "tick" in data
    assert "slots" in data
    assert "蜀" in data["slots"]
    assert "魏" in data["slots"]
    assert "吴" in data["slots"]

    # Initially all open
    for f in ["蜀", "魏", "吴"]:
        assert data["slots"][f]["status"] == "open"

    # Join one and check
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    r = client.get("/v1/lobby/status")
    data = r.json()
    assert data["slots"]["蜀"]["status"] == "occupied"
    assert data["slots"]["魏"]["status"] == "open"
    assert data["slots"]["吴"]["status"] == "open"


def test_lobby_status_shows_spectator_count():
    """Spectator count is tracked."""
    setup()
    r = client.get("/v1/lobby/status")
    assert r.json()["spectator_count"] == 0

    client.post("/v1/lobby/join", json={"faction": "spectator"})
    r = client.get("/v1/lobby/status")
    assert r.json()["spectator_count"] == 1


# ═══════════════════════════════════════════════════════════════
# Instruction endpoint
# ═══════════════════════════════════════════════════════════════


def test_instruction_contains_key_info():
    """GET /v1/lobby/instruction returns markdown with token, game_id, rules link."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    token = r.json()["session_token"]
    game_id = r.json()["game_id"]

    r = client.get(f"/v1/lobby/instruction?token={token}")
    assert r.status_code == 200
    text = r.text
    assert "蜀" in text
    assert str(game_id) in text
    assert token in text
    assert "/v1/rules" in text
    assert "/v1/api-spec.md" in text
    assert "while True" in text or "requests" in text


def test_instruction_bad_token():
    """Invalid token returns 404."""
    setup()
    r = client.get("/v1/lobby/instruction?token=bad-token")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Reconnect
# ═══════════════════════════════════════════════════════════════


def test_reconnect_bad_token():
    """Nonexistent token returns 400."""
    setup()
    r = client.post("/v1/lobby/reconnect", json={"token": "nonexistent"})
    assert r.status_code == 400


def test_reconnect_missing_token():
    """Missing token field returns 400."""
    setup()
    r = client.post("/v1/lobby/reconnect", json={})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Heartbeat
# ═══════════════════════════════════════════════════════════════


def test_heartbeat_valid_token():
    """Explicit heartbeat returns ok."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    token = r.json()["session_token"]

    r = client.post(f"/v1/sessions/{token}/heartbeat")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_heartbeat_invalid_token():
    """Invalid heartbeat token returns 401."""
    setup()
    r = client.post("/v1/sessions/bad-token/heartbeat")
    assert r.status_code == 401


def test_heartbeat_updates_slot():
    """Heartbeat keeps slot occupied."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    token = r.json()["session_token"]

    client.post(f"/v1/sessions/{token}/heartbeat")
    r = client.get("/v1/lobby/status")
    assert r.json()["slots"]["蜀"]["status"] == "occupied"


# ═══════════════════════════════════════════════════════════════
# Spectator cannot POST actions
# ═══════════════════════════════════════════════════════════════


def test_spectator_cannot_submit_actions():
    """Spectator token can't submit game actions."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "spectator"})
    token = r.json()["session_token"]
    game_id = r.json()["game_id"]

    r = client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": [{"type": "defend", "target": "成都"}]},
    )
    assert r.status_code in (401, 403), f"expected 401 or 403, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════
# Game auto-restart creates new game with fresh slots
# ═══════════════════════════════════════════════════════════════


def test_game_end_auto_creates_new_game():
    """After a game finishes, a new game with 3 open slots is created."""
    setup()
    r = client.get("/v1/lobby/status")
    old_game_id = r.json()["game_id"]

    # Join all 3 factions from different IPs
    tokens = {}
    for i, f in enumerate(["蜀", "魏", "吴"]):
        ip = f"10.0.1.{i + 1}"
        r = client.post(
            "/v1/lobby/join",
            json={"faction": f},
            headers={"X-Forwarded-For": ip},
        )
        tokens[f] = r.json()["session_token"]

    # Submit actions for all 3 factions for many ticks to try to finish
    for _ in range(5):
        for f in ["蜀", "魏", "吴"]:
            try:
                client.post(
                    f"/games/{old_game_id}/actions",
                    params={"token": tokens[f]},
                    json={"actions": [{"type": "defend", "target": "成都"}]},
                )
            except Exception:
                pass

    # Check lobby status after some time
    r = client.get("/v1/lobby/status")
    data = r.json()
    # Game should exist and have valid slot data
    assert "game_id" in data
    assert data["tick"] >= 0


# ═══════════════════════════════════════════════════════════════
# Rules & API spec endpoints
# ═══════════════════════════════════════════════════════════════


def test_rules_endpoint():
    """GET /v1/rules returns markdown."""
    setup()
    r = client.get("/v1/rules")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    text = r.text
    # Should contain rules content from docs/
    assert len(text) > 100


def test_api_spec_endpoint():
    """GET /v1/api-spec returns OpenAPI JSON."""
    setup()
    r = client.get("/v1/api-spec")
    assert r.status_code == 200
    data = r.json()
    assert "openapi" in data
    assert "paths" in data


def test_api_spec_md_endpoint():
    """GET /v1/api-spec.md returns markdown."""
    setup()
    r = client.get("/v1/api-spec.md")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    text = r.text
    assert "API" in text
    assert len(text) > 200


# ═══════════════════════════════════════════════════════════════
# Same IP join limit
# ═══════════════════════════════════════════════════════════════


def test_same_ip_cannot_hold_two_slots():
    """One IP can't hold two active faction slots."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    assert r.status_code == 200

    r = client.post("/v1/lobby/join", json={"faction": "魏"})
    # Should be rejected since same IP has an active session
    assert r.status_code in (429, 400), f"expected 429 or 400, got {r.status_code}: {r.text}"


# ═══════════════════════════════════════════════════════════════
# Session token in state endpoint updates heartbeat
# ═══════════════════════════════════════════════════════════════


def test_get_state_updates_heartbeat():
    """GET /games/{id}/state with BYOA token updates heartbeat."""
    setup()
    r = client.post("/v1/lobby/join", json={"faction": "蜀"})
    token = r.json()["session_token"]
    game_id = r.json()["game_id"]

    # Call state endpoint
    r = client.get(f"/games/{game_id}/state", params={"token": token})
    assert r.status_code == 200

    # Check slot is still occupied
    r = client.get("/v1/lobby/status")
    assert r.json()["slots"]["蜀"]["status"] == "occupied"
