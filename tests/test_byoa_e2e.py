"""Phase 5 — BYOA end-to-end tests. Bridges lobby API and game API."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, engine
from sqlmodel import SQLModel

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


def _tick(game_id: int):
    return client.post(f"/games/{game_id}/tick?token=admin-dev-token")


def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    return r.json()


def _get_state(game_id: int, token: str) -> dict:
    r = client.get(f"/games/{game_id}/state", params={"token": token})
    return r


def _submit_actions(game_id: int, token: str, actions: list[dict]) -> dict:
    r = client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": actions},
    )
    return r


# ═══════════════════════════════════════════════════════════════
# Full BYOA flow
# ═══════════════════════════════════════════════════════════════


def test_full_byoa_flow():
    """Join 3 factions via BYOA lobby, then run a multi-tick game loop."""
    setup()

    # Join all 3 factions from different IPs
    factions = {}
    for i, faction in enumerate(["蜀", "魏", "吴"]):
        ip = f"10.0.1.{i + 1}"
        result = _join(faction, ip)
        assert "session_token" in result, f"join {faction}: {result}"
        assert result["faction"] == faction
        assert result["game_id"] > 0
        factions[faction] = result

    gid = factions["蜀"]["game_id"]

    # Fetch instruction for each faction
    for faction, data in factions.items():
        r = client.get(f"/v1/lobby/instruction?token={data['session_token']}")
        assert r.status_code == 200
        text = r.text
        assert faction in text
        assert str(gid) in text
        assert data["session_token"] in text

    # Verify lobby status shows all 3 occupied
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200
    status_data = r.json()
    for faction in ["蜀", "魏", "吴"]:
        assert status_data["slots"][faction]["status"] == "occupied"

    # Run 3 ticks with actions
    for _ in range(3):
        for faction, data in factions.items():
            token = data["session_token"]
            # Fetch state
            r = _get_state(gid, token)
            assert r.status_code == 200, f"state for {faction}: {r.status_code}"
            state = r.json()
            assert "your_cities" in state
            assert "valid_actions" in state

            # Submit defend actions (safe, always valid)
            defends = [a for a in state.get("valid_actions", []) if a["type"] == "defend"]
            if defends:
                r = _submit_actions(gid, token, [{"type": "defend", "target": defends[0]["target"]}])
                assert r.status_code == 200, f"submit for {faction}: {r.status_code} {r.text[:100]}"

        # Advance tick
        r = _tick(gid)
        assert r.status_code == 200, f"tick: {r.status_code} {r.text[:100]}"

    # Verify game progressed
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200
    final_status = r.json()
    assert final_status["tick"] >= 3


def test_spectator_full_flow():
    """Spectator can see lobby status and game state, but cannot submit actions."""
    setup()

    # Join as spectator
    r = client.post("/v1/lobby/join", json={"faction": "spectator"})
    assert r.status_code == 200
    spec_data = r.json()
    assert spec_data["faction"] == "spectator"
    spec_token = spec_data["session_token"]
    gid = spec_data["game_id"]

    # Spectator can see lobby status
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200
    assert r.json()["spectator_count"] >= 1

    # Spectator tries to fetch game state (may or may not be allowed)
    r = client.get(f"/games/{gid}/state", params={"token": spec_token})
    # OK if spectator can view, or if blocked (depends on auth model)
    assert r.status_code in (200, 401, 403)

    # Spectator CANNOT submit actions
    r = client.post(
        f"/games/{gid}/actions",
        params={"token": spec_token},
        json={"actions": [{"type": "defend", "target": "成都"}]},
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


def test_reconnect_flow():
    """Session reconnects within grace period."""
    setup()

    # Join a faction
    data = _join("蜀", "10.0.2.1")
    token = data["session_token"]
    gid = data["game_id"]

    # Verify slot occupied
    r = client.get("/v1/lobby/status")
    assert r.json()["slots"]["蜀"]["status"] == "occupied"

    # Simulate disconnect by directly manipulating the session in DB
    # (We can't easily simulate heartbeat timeout in TestClient, so test reconnect API directly)
    # First verify reconnect works for an active session
    r = client.post("/v1/lobby/reconnect", json={"token": token})
    assert r.status_code == 200, f"reconnect: {r.status_code} {r.text[:100]}"
    assert r.json()["status"] == "reconnected"

    # Bad token => 400
    r = client.post("/v1/lobby/reconnect", json={"token": "bad-token"})
    assert r.status_code == 400

    # Missing token => 400
    r = client.post("/v1/lobby/reconnect", json={})
    assert r.status_code == 400


def test_action_validation():
    """Submit invalid actions and verify 400 responses."""
    setup()

    data = _join("蜀", "10.0.3.1")
    token = data["session_token"]
    gid = data["game_id"]

    # Join other factions so the game can tick
    _join("魏", "10.0.3.2")
    _join("吴", "10.0.3.3")

    # Bad: attack from a city not owned
    r = _submit_actions(gid, token, [
        {"type": "attack", "from": "洛阳", "target": "宛城", "troops": 100}
    ])
    assert r.status_code == 400, f"expected 400, got {r.status_code}"

    # Bad: zero troops
    r = _submit_actions(gid, token, [
        {"type": "attack", "from": "成都", "target": "宛城", "troops": 0}
    ])
    assert r.status_code == 400, f"expected 400, got {r.status_code}"

    # Bad: invalid diplomacy type
    r = _submit_actions(gid, token, [
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "invalid_type", "message": "hi"}
    ])
    assert r.status_code == 400, f"expected 400, got {r.status_code}"

    # Bad: empty actions
    r = _submit_actions(gid, token, [])
    assert r.status_code == 400, f"expected 400, got {r.status_code}"


def test_alliance_e2e():
    """Full alliance flow: propose → accept → verify shared info."""
    setup()

    # Join all three factions
    shu = _join("蜀", "10.0.4.1")
    wu = _join("吴", "10.0.4.2")
    wei = _join("魏", "10.0.4.3")
    gid = shu["game_id"]

    # Shu proposes alliance to Wu
    r = _submit_actions(gid, shu["session_token"], [
        {"type": "diplomacy", "target": "吴", "diplomacy_type": "alliance_propose", "message": "蜀吴联盟"}
    ])
    assert r.status_code == 200, f"propose: {r.status_code} {r.text[:100]}"

    # Wei submits defend (needed for tick)
    _submit_actions(gid, wei["session_token"], [{"type": "defend", "target": "邺城"}])

    # Tick to process proposal
    _tick(gid)

    # Wu accepts alliance
    r = _submit_actions(gid, wu["session_token"], [
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "同意联盟"}
    ])
    assert r.status_code == 200, f"accept: {r.status_code} {r.text[:100]}"

    # Wei defends, then tick
    _submit_actions(gid, wei["session_token"], [{"type": "defend", "target": "邺城"}])
    _tick(gid)

    # Verify alliance is active
    r = client.get(f"/games/{gid}/state", params={"token": shu["session_token"]})
    assert r.status_code == 200
    state = r.json()
    allies = state.get("your_alliance_with", [])
    assert "吴" in allies, f"Shu should be allied with Wu, got allies: {allies}"


def test_heartbeat_keeps_session_alive():
    """Heartbeat updates the session and keeps slot occupied."""
    setup()

    data = _join("蜀", "10.0.5.1")
    token = data["session_token"]

    # Send heartbeat
    r = client.post(f"/v1/sessions/{token}/heartbeat")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Slot should still be occupied
    r = client.get("/v1/lobby/status")
    assert r.json()["slots"]["蜀"]["status"] == "occupied"


def test_game_state_updates_heartbeat():
    """GET /games/{id}/state with BYOA token implicitly updates heartbeat."""
    setup()

    data = _join("蜀", "10.0.6.1")
    token = data["session_token"]
    gid = data["game_id"]

    # State fetch should NOT fail due to auth and should update heartbeat
    r = client.get(f"/games/{gid}/state", params={"token": token})
    assert r.status_code == 200, f"state: {r.status_code} {r.text[:100]}"

    # Verify slot still occupied
    r = client.get("/v1/lobby/status")
    assert r.json()["slots"]["蜀"]["status"] == "occupied"
