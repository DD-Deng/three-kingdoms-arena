"""Battle report API tests — P1-6: result, commentary, replay."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel, Session, select
from app.database import engine
from app.models import Game

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


# ═══════════════════════════════════════════════════════════════
# Test 1: In-progress game returns 425
# ═══════════════════════════════════════════════════════════════

def test_result_in_progress_returns_425(monkeypatch):
    """Requesting result of active game returns 425 Too Early."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀")

    r = client.get("/v1/games/1/result")
    assert r.status_code == 425, f"Expected 425, got {r.status_code}: {r.text}"
    assert "progress" in r.json().get("detail", "").lower()


# ═══════════════════════════════════════════════════════════════
# Test 2: Finished game returns 200 + full JSON
# ═══════════════════════════════════════════════════════════════

def test_result_finished_game_returns_200(monkeypatch):
    """Requesting result of finished game returns full summary."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Run a tick to generate log data
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit("token_wei", actions=[{"type": "defend", "target": "洛阳"}])
    _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Force-finish the game
    with Session(engine) as session:
        game = session.get(Game, 1)
        game.status = "finished"
        game.winner = "蜀"
        game.finished_at = "2026-05-15T12:00:00+00:00"
        session.add(game)
        session.commit()

    r = client.get("/v1/games/1/result")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    assert data["game_id"] == 1
    assert data["status"] == "finished"
    assert data["winner"] == "蜀"
    assert "winner_reason" in data
    assert "final_cities" in data
    assert "faction_stats" in data
    assert "key_events" in data
    assert "tick_finished" in data
    assert "commentary_url" in data
    assert "replay_url" in data

    # faction_stats should have all 3 factions
    for f in ["蜀", "魏", "吴"]:
        assert f in data["faction_stats"], f"{f} missing from faction_stats"


# ═══════════════════════════════════════════════════════════════
# Test 3: Non-existent game returns 404
# ═══════════════════════════════════════════════════════════════

def test_result_nonexistent_game_returns_404(monkeypatch):
    """Requesting result of non-existent game returns 404."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    r = client.get("/v1/games/9999/result")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Test 4: Commentary returns 202 when not available
# ═══════════════════════════════════════════════════════════════

def test_commentary_returns_202(monkeypatch):
    """Commentary endpoint returns 202 when commentary not yet generated."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀")

    # Force-finish the game
    with Session(engine) as session:
        game = session.get(Game, 1)
        game.status = "finished"
        game.winner = "蜀"
        game.finished_at = "2026-05-15T12:00:00+00:00"
        session.add(game)
        session.commit()

    r = client.get("/v1/games/1/commentary")
    assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
    assert "生成" in r.json().get("detail", "")


# ═══════════════════════════════════════════════════════════════
# Test 5: Replay returns tick data
# ═══════════════════════════════════════════════════════════════

def test_replay_returns_ticks(monkeypatch):
    """Replay endpoint returns per-tick public state array."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Run a few ticks to generate log data
    for i in range(2):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit("token_wei", actions=[{"type": "defend", "target": "洛阳"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
        _tick()

    r = client.get("/v1/games/1/replay")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    assert data["game_id"] == 1
    assert "total_ticks" in data
    assert "ticks" in data
    assert data["total_ticks"] > 0
    # Each tick entry has expected fields
    for t in data["ticks"]:
        assert "tick" in t
        assert "cities" in t
        assert "events" in t
        assert "diplomacy" in t


# ═══════════════════════════════════════════════════════════════
# Test 6: Replay for non-existent game returns 404
# ═══════════════════════════════════════════════════════════════

def test_replay_nonexistent_returns_404(monkeypatch):
    """Replay for non-existent game returns 404."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    r = client.get("/v1/games/9999/replay")
    assert r.status_code == 404
