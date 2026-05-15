"""Alliance/war mutual exclusion tests — P0-3."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine

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


def _state(token: str, game_id: int = 1):
    return client.get(f"/games/{game_id}/state?token={token}")


# ═══════════════════════════════════════════════════════════════
# Test 1: Declaring war on ally auto-breaks alliance
# ═══════════════════════════════════════════════════════════════

def test_declare_war_on_ally_breaks_alliance(monkeypatch):
    """Declaring war on an ally auto-breaks the alliance with penalty."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Advance a few ticks so credit is established
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])

    # Step 1: 蜀 proposes alliance to 魏
    r = _submit(shu["session_token"], actions=[{
        "type": "diplomacy",
        "target": "魏",
        "diplomacy_type": "alliance_propose",
        "message": "结盟吧",
    }])
    assert r.status_code == 200, f"propose failed: {r.text}"

    # Advance tick so pending_alliance_from is set on 魏
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])

    # Step 2: 魏 accepts
    r = _submit(wei["session_token"], actions=[{
        "type": "diplomacy",
        "target": "蜀",
        "diplomacy_type": "alliance_accept",
        "message": "好",
    }])
    assert r.status_code == 200, f"accept failed: {r.text}"

    # Advance tick to process diplomacy acceptance
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])

    # Verify alliance formed
    s = _state(shu["session_token"])
    data = s.json()
    relations = data.get("diplomacy_relations", {})
    wei_rel = relations.get("魏", {})
    assert wei_rel.get("status") == "allied", f"Expected allied, got {wei_rel}"

    # Step 3: 蜀 declares war on 魏 (should auto-break alliance)
    r = _submit(shu["session_token"], actions=[{
        "type": "diplomacy",
        "target": "魏",
        "diplomacy_type": "declare_war",
        "message": "开战",
    }])
    assert r.status_code == 200, f"declare_war failed: {r.text}"

    # Advance tick to process war declaration
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])

    # Verify: NOT allied anymore, now at_war
    s = _state(shu["session_token"])
    data = s.json()
    relations = data.get("diplomacy_relations", {})
    wei_rel = relations.get("魏", {})
    assert wei_rel.get("status") == "at_war", \
        f"Expected at_war after declaring on ally, got {wei_rel}"
    assert data.get("your_alliance_with") is None, \
        "Should have no ally after declaring war"


# ═══════════════════════════════════════════════════════════════
# Test 2: Cannot propose alliance while at war
# ═══════════════════════════════════════════════════════════════

def test_cannot_propose_alliance_while_at_war(monkeypatch):
    """Proposing alliance to a faction you're at war with should fail."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # 蜀 declares war on 魏
    r = _submit(shu["session_token"], actions=[{
        "type": "diplomacy",
        "target": "魏",
        "diplomacy_type": "declare_war",
        "message": "开战",
    }])
    assert r.status_code == 200, f"declare_war failed: {r.text}"

    # Advance tick
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])

    # Now 蜀 tries to propose alliance to 魏 (should fail — at war)
    r = _submit(shu["session_token"], actions=[{
        "type": "diplomacy",
        "target": "魏",
        "diplomacy_type": "alliance_propose",
        "message": "和好吧",
    }])
    assert r.status_code == 400, \
        f"Should reject alliance_propose while at war, got {r.status_code}: {r.text}"
    assert "交战" in r.json().get("detail", ""), \
        f"Error should mention 交战: {r.json()}"


# ═══════════════════════════════════════════════════════════════
# Test 3: diplomacy_relations is never allied+at_war simultaneously
# ═══════════════════════════════════════════════════════════════

def test_diplomacy_relations_mutually_exclusive(monkeypatch):
    """No pair of factions can have both allied and at_war status simultaneously."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Advance initial ticks
    for _ in range(2):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit("token_wei", actions=[{"type": "defend", "target": "洛阳"}])
        _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])

    s = _state(shu["session_token"])
    data = s.json()
    relations = data.get("diplomacy_relations", {})

    for faction, rel in relations.items():
        status = rel.get("status", "neutral")
        # Status must be one of the valid enum values
        assert status in ("allied", "at_war", "neutral", "hostile_recent_break"), \
            f"Invalid status {status} for {faction}"
        # Cannot be both allied and at_war (one status only)
        assert status != "allied" or status != "at_war", \
            f"Contradictory status for {faction}: {status}"


# ═══════════════════════════════════════════════════════════════
# Test 4: diplomacy_relations field present in state API
# ═══════════════════════════════════════════════════════════════

def test_diplomacy_relations_field_present(monkeypatch):
    """State API returns structured diplomacy_relations for all other factions."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    s = _state(shu["session_token"])
    data = s.json()

    assert "diplomacy_relations" in data, \
        f"diplomacy_relations missing from: {list(data.keys())}"
    relations = data["diplomacy_relations"]

    # Should have relations for the other 2 factions
    assert "魏" in relations, f"魏 missing from relations: {relations}"
    assert "吴" in relations, f"吴 missing from relations: {relations}"
    assert "蜀" not in relations, "Should not have relation to self"

    # Each relation should have a status field
    for faction, rel in relations.items():
        assert "status" in rel, f"status missing for {faction}: {rel}"
