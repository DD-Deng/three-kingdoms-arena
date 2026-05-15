"""Defense level visibility tests — Step 1: 防御度信息对称化."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel, Session, select
from app.database import engine
from app.models import Game, Agent

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


def _state(token: str, game_id: int = 1):
    return client.get(f"/games/{game_id}/state?token={token}")


# ═══════════════════════════════════════════════════════════════
# Test 1: Own cities show exact defense_level
# ═══════════════════════════════════════════════════════════════

def test_own_cities_defense_level_exact(monkeypatch):
    """Own cities always show exact defense_level."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Run 3 defends to build up defense works
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state: {s.text}"
    data = s.json()

    for c in data["your_cities"]:
        assert "defense_level" in c, f"defense_level missing from own city {c['name']}: {list(c.keys())}"
        assert isinstance(c["defense_level"], int), f"defense_level should be int: {c['defense_level']}"
        assert "defense_status" in c, f"defense_status missing from own city {c['name']}"
        assert c["defense_status"] in ("fortified", "normal", "exposed"), \
            f"Invalid defense_status: {c['defense_status']}"


# ═══════════════════════════════════════════════════════════════
# Test 2: Adjacent enemy cities show exact defense_level
# ═══════════════════════════════════════════════════════════════

def test_adjacent_enemy_defense_level_exact(monkeypatch):
    """Cities adjacent to own territory show exact defense_level."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Wei defends 洛阳 (adjacent to 长安 which Shu owns) several times
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
        _tick()

    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state: {s.text}"
    data = s.json()

    # 洛阳 should be adjacent to Shu's 长安
    luoyang = next((c for c in data["known_cities"] if c["name"] == "洛阳"), None)
    assert luoyang is not None, "洛阳 should be in Shu's known_cities"
    assert luoyang["info_freshness"] == "current", f"洛阳 should be current, got {luoyang.get('info_freshness')}"
    assert "defense_level" in luoyang, \
        f"defense_level missing from adjacent city 洛阳: {list(luoyang.keys())}"
    assert isinstance(luoyang["defense_level"], int)
    assert luoyang["defense_level"] >= 0


# ═══════════════════════════════════════════════════════════════
# Test 3: Non-adjacent cities only show defense_status
# ═══════════════════════════════════════════════════════════════

def test_non_adjacent_enemy_defense_status_only(monkeypatch):
    """Cities not adjacent to own territory do NOT expose defense_level, only defense_status."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Wei defends 邺城 (not adjacent to Shu's cities)
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "邺城"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
        _tick()

    # 蜀 has no adjacent cities with 邺城, so 邺城 should be a rumor
    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state: {s.text}"
    data = s.json()

    yecheng = next((c for c in data["known_cities"] if c["name"] == "邺城"), None)
    if yecheng and yecheng.get("info_freshness") == "current":
        # If somehow visible (e.g., war revealed), should NOT have defense_level
        # unless it's adjacent
        assert "defense_level" not in yecheng, \
            f"Non-adjacent city 邺城 should not expose defense_level: {yecheng}"
        assert "defense_status" in yecheng, \
            f"defense_status missing from non-adjacent city: {list(yecheng.keys())}"
    elif yecheng and yecheng.get("info_freshness") == "rumor":
        # Rumor cities get defense_status too
        assert "defense_status" in yecheng, \
            f"Rumor cities should have defense_status: {list(yecheng.keys())}"
        assert "defense_level" not in yecheng, \
            f"Rumor cities should not expose defense_level: {yecheng}"


# ═══════════════════════════════════════════════════════════════
# Test 4: Alliance cities show exact defense_level even if not adjacent
# ═══════════════════════════════════════════════════════════════

def test_alliance_cities_defense_level_exact(monkeypatch):
    """Alliance partner cities show exact defense_level regardless of distance."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Build defense on 邺城 (Wei's distant city)
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "邺城"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
        _tick()

    # Form alliance: Shu proposes to Wei
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Wei accepts
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
    _tick()

    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state: {s.text}"
    data = s.json()

    assert data.get("your_alliance_with") == "魏", f"Should be allied with 魏: {data}"

    # 邺城 should now be visible with exact defense_level (because Wei is ally)
    yecheng = next((c for c in data["known_cities"] if c["name"] == "邺城"), None)
    assert yecheng is not None, "邺城 should be in known_cities (alliance)"
    assert yecheng.get("info_freshness") == "current", \
        f"Ally city should be current: {yecheng}"
    assert "defense_level" in yecheng, \
        f"Ally city 邺城 should expose defense_level: {list(yecheng.keys())}"
    assert isinstance(yecheng["defense_level"], int)
    assert yecheng["defense_level"] >= 0


# ═══════════════════════════════════════════════════════════════
# Step 3: Nerf defense works
# ═══════════════════════════════════════════════════════════════

def test_defense_level_capped_at_3(monkeypatch):
    """Defending 5 times should cap defense_level at 3."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    for _ in range(5):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    s = _state(shu["session_token"])
    data = s.json()

    chengdu = next((c for c in data["your_cities"] if c["name"] == "成都"), None)
    assert chengdu is not None
    assert chengdu["defense_level"] <= 3, f"Expected <= 3, got {chengdu['defense_level']}"
    assert chengdu["defense_level"] == 3, f"After 5 defends, expected cap at 3, got {chengdu['defense_level']}"


def test_defense_bonus_15_percent(monkeypatch):
    """D3 defense should give 1.45x multiplier (not 2.0x)."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    from app.engine import DEFENSE_WORKS_MAX, DEFENSE_WORKS_BONUS

    assert DEFENSE_WORKS_MAX == 3, f"DEFENSE_WORKS_MAX should be 3, got {DEFENSE_WORKS_MAX}"
    assert DEFENSE_WORKS_BONUS == 0.15, f"DEFENSE_WORKS_BONUS should be 0.15, got {DEFENSE_WORKS_BONUS}"

    # D3 multiplier
    multiplier = 1.0 + 3 * DEFENSE_WORKS_BONUS
    assert multiplier == 1.45, f"D3 multiplier should be 1.45, got {multiplier}"
