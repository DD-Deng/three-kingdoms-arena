"""Phase 1 — Ready / Countdown tests."""

import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, engine
from sqlmodel import SQLModel, Session, select
from app.models import Game, Slot

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


def _make_lobby_game():
    """Create a game in 'lobby' status with 3 open slots via direct DB access."""
    from app.models import Player, RegisteredAgent, Agent
    from app.engine import MANAGED_DEFAULTS, ALL_CITIES, INITIAL_SETUP, FACTION_POOL, City
    from app.engine import TRUST_INITIAL, INITIAL_GRAIN
    import json

    with Session(engine) as session:
        # Mark all existing games as not current
        old = session.exec(select(Game).where(Game.is_current == True)).all()
        for g in old:
            g.is_current = False
            session.add(g)

        game = Game(
            mode="pvp",
            status="lobby",
            auto_advance=True,
            max_ticks=50,
            is_current=True,
            is_active=True,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(game)
        session.flush()

        # Init cities
        for name in ALL_CITIES:
            owner, troops = INITIAL_SETUP[name]
            session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

        resources = {
            f: {"grain": INITIAL_GRAIN.get(f, 500), "debt": 0, "trust_score": TRUST_INITIAL}
            for f in FACTION_POOL
        }
        game.resources = json.dumps(resources, ensure_ascii=False)
        session.add(game)

        # Create managed agents + slots
        for faction in FACTION_POOL:
            cfg = MANAGED_DEFAULTS[faction]
            player = Player()
            session.add(player)
            session.flush()
            reg = RegisteredAgent(player_id=player.player_id, agent_name=cfg["name"])
            session.add(reg)
            session.flush()
            agent = Agent(
                game_id=game.id,
                registered_agent_id=reg.agent_id,
                agent_name=cfg["name"],
                faction=faction,
                agent_mode="managed",
                persona_config=cfg["persona"],
            )
            session.add(agent)

            slot = Slot(game_id=game.id, faction=faction, status="open")
            session.add(slot)

        session.commit()
        gid = game.id
    return gid


def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction, "agent_display_name": f"TestAgent-{faction}"},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


# ═══════════════════════════════════════════════════════════════
# Ready endpoint
# ═══════════════════════════════════════════════════════════════


def test_ready_single_faction(monkeypatch):
    """A single faction can declare ready. Countdown does NOT start yet (need 3)."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")

    r = client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ready"
    assert data["all_ready"] == False
    assert data["countdown_started"] == False


def test_ready_all_three_triggers_countdown(monkeypatch):
    """When all 3 occupied slots declare ready, countdown starts."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    r1 = client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    assert r1.status_code == 200
    r2 = client.post("/v1/lobby/ready", json={"token": wei["session_token"]})
    assert r2.status_code == 200

    # Third ready triggers countdown
    r3 = client.post("/v1/lobby/ready", json={"token": wu["session_token"]})
    assert r3.status_code == 200, r3.text
    data = r3.json()
    assert data["status"] == "ready"
    assert data["all_ready"] == True
    assert data["countdown_started"] == True
    assert data["countdown_deadline"] is not None


def test_ready_idempotent():
    """Calling ready twice returns already_ready."""
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")

    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    r = client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    assert r.status_code == 200
    assert r.json()["status"] == "already_ready"


def test_ready_without_token():
    """Ready without token returns 400."""
    setup()
    r = client.post("/v1/lobby/ready", json={})
    assert r.status_code == 400


def test_ready_spectator_rejected(monkeypatch):
    """Spectator cannot declare ready."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()
    r = client.post("/v1/lobby/join", json={"faction": "spectator"})
    token = r.json()["session_token"]

    r = client.post("/v1/lobby/ready", json={"token": token})
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# Unready endpoint
# ═══════════════════════════════════════════════════════════════


def test_unready_reverts_countdown(monkeypatch):
    """Cancelling ready during countdown returns game to lobby."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # All 3 ready → countdown
    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wei["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wu["session_token"]})

    # One unready → back to lobby
    r = client.post("/v1/lobby/unready", json={"token": shu["session_token"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "unready"
    assert data["game_status"] == "lobby"


def test_unready_not_ready():
    """Unready when not ready returns not_ready."""
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")

    r = client.post("/v1/lobby/unready", json={"token": shu["session_token"]})
    assert r.status_code == 200
    assert r.json()["status"] == "not_ready"


# ═══════════════════════════════════════════════════════════════
# Lobby status — ready fields
# ═══════════════════════════════════════════════════════════════


def test_lobby_status_shows_ready_fields(monkeypatch):
    """Lobby status includes ready, agent_display_name, countdown fields."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()

    # Join one faction
    shu = _join("蜀", "10.0.0.1")

    # Check lobby status before ready
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200
    data = r.json()
    assert "countdown_started_at" in data
    assert "countdown_deadline" in data
    assert data["slots"]["蜀"]["status"] == "occupied"
    assert data["slots"]["蜀"]["ready"] == False
    assert data["slots"]["蜀"].get("agent_display_name") == "TestAgent-蜀"

    # After ready
    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    r = client.get("/v1/lobby/status")
    data = r.json()
    assert data["slots"]["蜀"]["ready"] == True


def test_lobby_status_includes_countdown(monkeypatch):
    """When countdown is active, lobby status shows the deadline."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wei["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wu["session_token"]})

    r = client.get("/v1/lobby/status")
    data = r.json()
    assert data["status"] == "countdown"
    assert data["countdown_deadline"] is not None


# ═══════════════════════════════════════════════════════════════
# Countdown→active transition
# ═══════════════════════════════════════════════════════════════


def test_countdown_expires_game_becomes_active(monkeypatch):
    """When countdown deadline passes, game transitions to active via pvp_maybe_advance."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    monkeypatch.setattr("app.config.COUNTDOWN_SEC", 1)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wei["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wu["session_token"]})

    # Wait for countdown to expire
    time.sleep(1.5)

    # Polling lobby status drives pvp_maybe_advance → countdown→active
    r = client.get("/v1/lobby/status")
    data = r.json()
    assert data["status"] == "active", f"Expected active, got {data['status']}"


def test_countdown_pending_before_deadline(monkeypatch):
    """Before countdown deadline, game stays in countdown."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 999)
    monkeypatch.setattr("app.config.COUNTDOWN_SEC", 60)
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    client.post("/v1/lobby/ready", json={"token": shu["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wei["session_token"]})
    client.post("/v1/lobby/ready", json={"token": wu["session_token"]})

    r = client.get("/v1/lobby/status")
    assert r.json()["status"] == "countdown"


# ═══════════════════════════════════════════════════════════════
# Instruction template includes ready flow
# ═══════════════════════════════════════════════════════════════


def test_instruction_includes_ready_flow():
    """Instruction template includes ready/unready endpoints and countdown info."""
    setup()
    _make_lobby_game()
    shu = _join("蜀", "10.0.0.1")

    r = client.get(f"/v1/lobby/instruction?token={shu['session_token']}")
    assert r.status_code == 200
    text = r.text
    assert "/v1/lobby/ready" in text
    assert "/v1/lobby/unready" in text
    assert "倒计时" in text
    assert "countdown_deadline" in text
